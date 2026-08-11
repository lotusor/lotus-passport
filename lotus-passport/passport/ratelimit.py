"""
Redis-backed rate limiting + OAuth state store.

Both use short-lived keys with TTL so a crash can never leave stale locks.
In tests (settings.TESTING) a fakeredis instance is used transparently.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from django.conf import settings

try:  # pragma: no cover - import side effect only
    import redis
except Exception:  # noqa: BLE001  (redis missing falls back at call time)
    redis = None  # type: ignore

try:
    import fakeredis
except Exception:  # noqa: BLE001
    fakeredis = None  # type: ignore


_CLIENT: Any = None


def get_redis() -> Any:
    """Lazily build the Redis client.

    * pytest (TESTING=True) → fakeredis (always)
    * DEBUG=True (dev runserver) → fakeredis (no real Redis needed)
    * Production → real Redis from REDIS_URL
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    use_fake = getattr(settings, "TESTING", False) or getattr(settings, "DEBUG", False)
    if use_fake and fakeredis is not None:
        _CLIENT = fakeredis.FakeStrictRedis()
    else:
        if redis is None:
            raise RuntimeError("redis is not installed")
        _CLIENT = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _CLIENT


class RateLimiter:
    """Fixed-window counter: `limit` requests per `window` seconds per key."""

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or get_redis()

    def is_allowed(self, key: str, limit: int, window: int) -> bool:
        count = self.client.incr(key)
        if count == 1:
            self.client.expire(key, window)
        return count <= limit

    def remaining(self, key: str) -> int:
        return int(self.client.get(key) or 0)


def check_rate_limit(
    request: Any,
    limit: int,
    window: int,
    *,
    scope: str = "api",
    identifier: str | None = None,
) -> bool:
    """Return True if the request is allowed, else False (caller should 429).

    The rate-limit key is dimensioned on *identity*, not raw IP:
      * if ``identifier`` is given (e.g. the login ``identifier``) it drives
        the key — so hundreds of users behind one NAT IP are counted
        independently (fixes the campus/enterprise-NAT false-positive);
      * otherwise it falls back to the authenticated ``uid`` (already the case
        for authed endpoints) or, for anonymous flows, the IP.
    A separate coarse per-IP limit (scope="ip-coarse") is the server's edge
    defence; see ``PasswordLoginView``.
    """
    ip = request.META.get("REMOTE_ADDR", "0.0.0.0")
    if identifier:
        idkey = identifier
    else:
        user = getattr(request, "user", None)
        uid = (
            getattr(user, "passport_user_id", "")
            if user and getattr(user, "is_authenticated", False)
            else ""
        )
        idkey = uid or ip
    key = f"ratelimit:{scope}:{idkey}:{request.path}"
    return RateLimiter().is_allowed(key, limit, window)


class AccountLockout:
    """Per-identifier consecutive-failure counter (Redis-backed).

    After ``threshold`` failures within ``window`` seconds the identifier is
    considered locked. ``ttl`` reports the seconds remaining until the counter
    resets, which doubles as the client-facing ``retry_after``.
    """

    PREFIX = "lockout:login:"

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or get_redis()

    def _key(self, identifier: str) -> str:
        return f"{self.PREFIX}{identifier.lower()}"

    def register_failure(
        self, identifier: str, *, threshold: int = 5, window: int = 900
    ) -> tuple[int, int]:
        key = self._key(identifier)
        count = self.client.incr(key)
        if count == 1:
            self.client.expire(key, window)
        return count, int(self.client.ttl(key) or 0)

    def failures(self, identifier: str) -> int:
        return int(self.client.get(self._key(identifier)) or 0)

    def is_locked(self, identifier: str, *, threshold: int = 5) -> bool:
        return self.failures(identifier) >= threshold

    def ttl(self, identifier: str) -> int:
        return int(self.client.ttl(self._key(identifier)) or 0)

    def clear(self, identifier: str) -> None:
        self.client.delete(self._key(identifier))


class OAuthStateStore:
    """Stores the CSRF `state` for the OAuth redirect round-trip (TTL 10 min)."""

    PREFIX = "oauth:state:"
    TTL = 600

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or get_redis()

    def save(
        self,
        provider: str,
        redirect_uri: str = "",
        *,
        link_mode: bool = False,
        passport_id: str | None = None,
    ) -> str:
        state = uuid.uuid4().hex + uuid.uuid4().hex[:8]
        payload = json.dumps(
            {
                "provider": provider,
                "redirect_uri": redirect_uri,
                "link_mode": link_mode,
                "passport_id": passport_id,
            }
        )
        self.client.setex(f"{self.PREFIX}{state}", self.TTL, payload)
        return state

    def consume(self, state: str | None) -> dict[str, Any] | None:
        if not state:
            return None
        key = f"{self.PREFIX}{state}"
        raw = self.client.get(key)
        if not raw:
            return None
        self.client.delete(key)
        return json.loads(raw)

    def ttl(self, state: str) -> int:
        return int(self.client.ttl(f"{self.PREFIX}{state}") or 0)
