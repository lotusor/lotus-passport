"""JWKS fetching and caching.

Why this is more than ``requests.get(jwks_url).json()``:

* **Per-request fetches are a latency and availability disaster.** Every API call
  would depend on passport being up. We cache and only refresh on TTL expiry.
* **Key rotation must not need a redeploy.** An unknown ``kid`` triggers exactly
  one forced refresh, so a rotated key is picked up within seconds.
* **That refresh is itself an attack surface.** An attacker can mint garbage
  tokens with random ``kid`` values and turn your service into a JWKS flood
  against passport. ``min_refresh_interval`` throttles forced refreshes.
* **A dead passport must not nuke a warm cache.** If a refresh fails while we
  still hold usable keys, we log-and-keep rather than emptying the cache and
  401-ing every user.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .errors import JWKSError, UnknownSigningKey
from .transport import Transport

# Only asymmetric signature families. HS*/oct are rejected on purpose: if an
# HMAC "key" ever appeared in a public JWKS, anyone could read it and forge
# tokens (the classic algorithm-confusion attack).
_ALLOWED_KTY = {"RSA", "EC", "OKP"}


class JWKSCache:
    """Thread-safe cache of the signing keys published by Lotus Passport.

    Args:
        jwks_url: Absolute URL of the JWKS document.
        transport: HTTP transport used to fetch it.
        ttl: Seconds a fetched document is considered fresh.
        min_refresh_interval: Floor between two *forced* refreshes (unknown-kid
            path). Protects passport from a token-driven fetch flood.
        timeout: Per-request HTTP timeout in seconds.
        clock: Monotonic clock, injectable for tests.
    """

    def __init__(
        self,
        jwks_url: str,
        transport: Transport,
        *,
        ttl: float = 600.0,
        min_refresh_interval: float = 30.0,
        timeout: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.jwks_url = jwks_url
        self._transport = transport
        self._ttl = ttl
        self._min_refresh_interval = min_refresh_interval
        self._timeout = timeout
        self._clock = clock

        self._lock = threading.RLock()
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None
        self._last_forced: float = float("-inf")

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    @property
    def is_fresh(self) -> bool:
        with self._lock:
            return (
                self._fetched_at is not None
                and (self._clock() - self._fetched_at) < self._ttl
            )

    def key_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._keys)

    def get_key(self, kid: str | None) -> Any:
        """Return the verification key for ``kid``.

        Args:
            kid: ``kid`` from the token header. ``None`` is tolerated only when
                the JWKS holds exactly one key — otherwise the choice would be
                ambiguous and guessing is how verifiers get exploited.

        Returns:
            A key object accepted by ``jwt.decode``.

        Raises:
            UnknownSigningKey: ``kid`` is absent from the JWKS after a refresh.
            JWKSError: The document could not be fetched or contained no usable key.
        """
        with self._lock:
            if not self.is_fresh:
                self._refresh_locked(soft=True)

            key = self._lookup_locked(kid)
            if key is not None:
                return key

            # Unknown kid: could be a genuine rotation. One throttled retry.
            if self._may_force_locked():
                self._refresh_locked(soft=False)
                key = self._lookup_locked(kid)
                if key is not None:
                    return key

            raise UnknownSigningKey(
                f"No signing key for kid={kid!r}. Known kids: {sorted(self._keys) or '<empty>'}. "
                "Either the token was issued by a different service, or key rotation "
                "has not propagated yet."
            )

    def refresh(self) -> None:
        """Force a refresh, ignoring TTL (used by tests and admin endpoints)."""
        with self._lock:
            self._refresh_locked(soft=False, throttle=False)

    def clear(self) -> None:
        with self._lock:
            self._keys.clear()
            self._fetched_at = None

    # ------------------------------------------------------------------ #
    # internals (call with the lock held)
    # ------------------------------------------------------------------ #
    def _lookup_locked(self, kid: str | None) -> Any | None:
        if kid:
            return self._keys.get(kid)
        if len(self._keys) == 1:
            return next(iter(self._keys.values()))
        return None

    def _may_force_locked(self) -> bool:
        return (self._clock() - self._last_forced) >= self._min_refresh_interval

    def _refresh_locked(self, *, soft: bool, throttle: bool = True) -> None:
        """Fetch and parse the JWKS.

        Args:
            soft: When True a failure is swallowed **if** we still hold keys —
                a passport blip must not invalidate every session.
            throttle: Record this fetch against the forced-refresh throttle.
        """
        if throttle:
            self._last_forced = self._clock()
        try:
            status, body = self._transport.get_json(self.jwks_url, timeout=self._timeout)
        except Exception as exc:  # noqa: BLE001
            if soft and self._keys:
                return
            raise JWKSError(f"JWKS fetch failed: {exc}") from exc

        if status != 200 or not isinstance(body, dict):
            if soft and self._keys:
                return
            raise JWKSError(
                f"JWKS endpoint {self.jwks_url} returned HTTP {status} "
                f"with an unusable body.",
                status_code=status,
            )

        parsed = self._parse(body)
        if not parsed:
            if soft and self._keys:
                return
            raise JWKSError(f"JWKS document at {self.jwks_url} contains no usable key.")

        self._keys = parsed
        self._fetched_at = self._clock()

    @staticmethod
    def _parse(document: dict[str, Any]) -> dict[str, Any]:
        try:
            from jwt import PyJWK
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise JWKSError("PyJWT[crypto] is required to parse JWKS") from exc

        keys: dict[str, Any] = {}
        for entry in document.get("keys") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("kty") not in _ALLOWED_KTY:
                continue
            if entry.get("use") not in (None, "sig"):
                continue  # encryption keys must never verify signatures
            try:
                jwk = PyJWK.from_dict(entry)
            except Exception:  # noqa: BLE001 - one bad key must not kill the set
                continue
            kid = entry.get("kid") or ""
            keys[kid] = jwk.key
        return keys


__all__ = ["JWKSCache"]
