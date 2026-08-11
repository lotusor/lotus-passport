"""
Server-side token revocation (logout / "force sign-out").

Why this exists
---------------
Tokens are signed (RS256) and integrators verify them *offline* via JWKS, so a
token cannot be invalidated by simply deleting a server-side session. For a
unified auth center that still needs a real "logout" / "revoke this device"
capability, we keep a small Redis-backed blacklist keyed by the token's ``jti``
(Json Token Identifier). Each entry lives exactly as long as the token itself
(TTL = remaining lifetime), so the list stays tiny.

Scope & trade-off (documented in HANDOVER §7)
---------------------------------------------
* Enforced at passport's own endpoints (``/api/v1/userinfo/`` checks the jti).
* Integrators that verify tokens offline will only stop trusting a revoked
  token once it expires (access TTL is short — 30 min by default). This is the
  accepted cost of offline verification; the blast radius is bounded by the
  short access lifetime.
* If Redis is unavailable the store degrades *open* (revocation is skipped)
  rather than locking every user out — userinfo must never hard-fail on a Redis
  hiccup.
"""
from __future__ import annotations

from typing import Any

from .ratelimit import get_redis

_PREFIX = "token:bl:"


class RevocationStore:
    """jti blacklist backed by Redis (or fakeredis in dev/tests)."""

    def __init__(self, client: Any | None = None) -> None:
        try:
            self.client = client or get_redis()
            self.available = self.client is not None
        except Exception:  # noqa: BLE001
            self.client = None
            self.available = False

    def revoke(self, jti: str | None, ttl: int) -> bool:
        """Blacklist ``jti`` for ``ttl`` seconds. Returns True on success."""
        if not self.available or not jti:
            return False
        try:
            self.client.setex(f"{_PREFIX}{jti}", max(int(ttl), 1), "1")
            return True
        except Exception:  # noqa: BLE001
            return False

    def is_revoked(self, jti: str | None) -> bool:
        """True if ``jti`` is currently blacklisted. Fails open on errors."""
        if not self.available or not jti:
            return False
        try:
            return bool(self.client.exists(f"{_PREFIX}{jti}"))
        except Exception:  # noqa: BLE001
            return False
