"""
Redis-backed rate limiting + OAuth state store.

Both use short-lived keys with TTL so a crash can never leave stale locks.
In tests (settings.TESTING) a fakeredis instance is used transparently.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
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

logger = logging.getLogger(__name__)


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
        # Bounded timeouts are critical: without socket_timeout a single slow
        # / unreachable Redis blocks the whole worker until gunicorn kills it
        # (HTTP 500, no traceback, request appears to hang). Every Redis call
        # in this app is best-effort, so failing fast is always the right move.
        _CLIENT = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=3,
            socket_connect_timeout=3,
            socket_keepalive=True,
            retry_on_timeout=True,
            health_check_interval=30,
        )
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
    """Stores the CSRF `state` for the OAuth redirect round-trip (TTL 10 min).

    When the login was initiated with PKCE (RFC 7636), the ``code_challenge``
    and ``code_challenge_method`` ride along inside the state so the callback
    can issue a one-time *authorization code* instead of bouncing the tokens
    themselves through the browser.
    """

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
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> str:
        state = uuid.uuid4().hex + uuid.uuid4().hex[:8]
        payload = json.dumps(
            {
                "provider": provider,
                "redirect_uri": redirect_uri,
                "link_mode": link_mode,
                "passport_id": passport_id,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
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


class PendingConsentStore:
    """One-time ticket for the OAuth *authorization-consent* screen (外部应用接入).

    After the passport authenticates a user via a third-party provider on behalf
    of an *external* integrating app, we don't bounce the token straight back to
    the app. Instead we stash the just-issued tokens behind a single-use ticket
    and send the browser to the consent page; only after the user clicks
    "授权" does :class:`OAuthConsentView` 302 to the app's ``redirect_uri`` with
    the token in the URL fragment.

    The ticket is single-use (``consume`` deletes it) and TTL-bounded, so a crash
    or a user walking away leaves nothing sensitive behind.
    """

    PREFIX = "oauth:consent:"
    TTL = 600  # 10 min — same window as the OAuth state round-trip

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or get_redis()

    def save(
        self,
        *,
        redirect_uri: str,
        access: str,
        refresh: str,
        token_type: str,
        passport_user_id: str,
        provider: str,
        jti: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> str:
        ticket = uuid.uuid4().hex + uuid.uuid4().hex[:8]
        payload = json.dumps(
            {
                "redirect_uri": redirect_uri,
                "access": access,
                "refresh": refresh,
                "token_type": token_type,
                "passport_user_id": passport_user_id,
                "provider": provider,
                "jti": jti,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
            }
        )
        self.client.setex(f"{self.PREFIX}{ticket}", self.TTL, payload)
        return ticket

    def peek(self, ticket: str | None) -> dict[str, Any] | None:
        """Read without consuming — used by the consent page's GET render."""
        if not ticket:
            return None
        raw = self.client.get(f"{self.PREFIX}{ticket}")
        return json.loads(raw) if raw else None

    def consume(self, ticket: str | None) -> dict[str, Any] | None:
        """Single-use read: returns the payload and deletes the key, or None."""
        if not ticket:
            return None
        key = f"{self.PREFIX}{ticket}"
        raw = self.client.get(key)
        if not raw:
            return None
        self.client.delete(key)
        return json.loads(raw)


class PasswordResetStore:
    """One-time tokens for email-based password reset (§9.4a reset).

    ``save(uid)`` mints a random token bound to the user id with a TTL
    (default 30 min); ``consume(token)`` is single-use — reading it deletes it.
    Redis down means reset is unavailable (fail-closed for a security flow),
    surfaced as 503 by the views.
    """

    PREFIX = "pwreset:"
    TTL = 1800

    def __init__(self, client: Any | None = None, ttl: int | None = None) -> None:
        self.client = client or get_redis()
        self.ttl = ttl if ttl is not None else self.TTL

    def save(self, uid: int) -> str:
        token = uuid.uuid4().hex + uuid.uuid4().hex[:8]
        self.client.setex(f"{self.PREFIX}{token}", self.ttl, str(uid))
        return token

    def consume(self, token: str | None) -> int | None:
        """Return the user id bound to the token (single-use), or None."""
        if not token:
            return None
        key = f"{self.PREFIX}{token}"
        raw = self.client.get(key)
        if not raw:
            return None
        self.client.delete(key)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None


class EmailCodeStore:
    """One-time 6-digit email verification codes (登录/注册、绑定邮箱、换绑邮箱).

    ``save(email, purpose)`` mints a numeric code bound to (purpose, email)
    with a TTL of 10 minutes; ``verify(email, purpose, code)`` is single-use
    and caps wrong attempts at 5 before the code is invalidated (brute-force
    resistance). Send-frequency throttling lives in the views (60s / email /
    purpose + hourly cap), reusing :class:`RateLimiter`.
    """

    PREFIX = "emailcode:"
    TTL = 600
    MAX_ATTEMPTS = 5
    PURPOSES = ("login", "bind", "new", "old")

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or get_redis()

    def _key(self, email: str, purpose: str) -> str:
        return f"{self.PREFIX}{purpose}:{email.strip().lower()}"

    def save(self, email: str, purpose: str) -> str:
        code = f"{secrets.randbelow(1000000):06d}"
        payload = json.dumps({"code": code, "attempts": 0})
        self.client.setex(self._key(email, purpose), self.TTL, payload)
        return code

    def verify(self, email: str, purpose: str, code: str | None) -> bool:
        """Single-use check; wrong attempts increment until MAX_ATTEMPTS burns it."""
        if not code or not code.strip():
            return False
        key = self._key(email, purpose)
        raw = self.client.get(key)
        if not raw:
            return False
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            self.client.delete(key)
            return False
        if str(code).strip() == str(data.get("code")):
            self.client.delete(key)
            return True
        attempts = int(data.get("attempts", 0)) + 1
        if attempts >= self.MAX_ATTEMPTS:
            self.client.delete(key)
        else:
            self.client.setex(key, self.TTL, json.dumps({"code": data.get("code"), "attempts": attempts}))
        return False


class CaptchaGate:
    """Adaptive human-verification gate for the email-code send endpoint.

    Counts send-code *requests* on two independent dimensions — source IP and
    target email address — inside a fixed window. As soon as **either**
    dimension reaches its threshold, the caller must present a valid CAPTCHA
    token before a code is sent.

    Why two dimensions: a single host rotating through target addresses is
    caught by the IP counter; a distributed flood aimed at one victim mailbox
    is caught by the address counter. Neither dimension alone covers both, and
    the email-bombing threat model needs both.

    Counters use the same fixed-window semantics as :class:`RateLimiter` and
    expire on their own, so a gate that somehow got stuck can never outlive
    ``CAPTCHA_EMAIL_WINDOW``. :meth:`clear` resets the address dimension once a
    token has verified, so a legitimate user is not asked again for the same
    mailbox within the window (see :meth:`clear` for why the IP dimension is
    deliberately left alone).

    Failure mode: counting is *best-effort*. If Redis is unavailable the gate
    degrades to "not required" rather than blocking sends — the endpoint's
    primary controls (per-address cooldown + hourly cap) are still enforced, and
    a secondary control must not become a availability single point of failure.
    Failures are logged so the degradation is visible.
    """

    PREFIX = "captcha:gate:"

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or get_redis()

    # -- thresholds (read lazily so tests can override settings) ---------- #
    @staticmethod
    def _ip_threshold() -> int:
        return int(getattr(settings, "CAPTCHA_EMAIL_IP_THRESHOLD", 10))

    @staticmethod
    def _addr_threshold() -> int:
        return int(getattr(settings, "CAPTCHA_EMAIL_ADDR_THRESHOLD", 3))

    @staticmethod
    def _window() -> int:
        return int(getattr(settings, "CAPTCHA_EMAIL_WINDOW", 3600))

    # -- keys ------------------------------------------------------------- #
    @staticmethod
    def _ip_key(ip: str | None) -> str:
        return f"{CaptchaGate.PREFIX}ip:{ip or '0.0.0.0'}"

    @staticmethod
    def _addr_key(email: str) -> str:
        return f"{CaptchaGate.PREFIX}addr:{(email or '').strip().lower()}"

    # -- public API ------------------------------------------------------- #
    def required(self, ip: str | None, email: str) -> bool:
        """True when either dimension has already reached its threshold."""
        return (
            self._count(self._ip_key(ip)) >= self._ip_threshold()
            or self._count(self._addr_key(email)) >= self._addr_threshold()
        )

    def touch(self, ip: str | None, email: str) -> None:
        """Record one send-code request on both dimensions.

        Called for *every* request that reaches the endpoint (including ones
        later rejected by the cooldown), so a hammering client trips the gate
        quickly instead of only counting successful sends.
        """
        self._bump(self._ip_key(ip))
        self._bump(self._addr_key(email))

    def clear(self, email: str) -> None:
        """Reset the *address* dimension after a CAPTCHA token verifies.

        Only the address counter is cleared, deliberately. The address counter
        answers "has this mailbox been asked too often?" — once a human has
        proved they are driving the flow, nagging them again for the same
        mailbox is pure friction.

        The IP counter answers "is this host behaving like a bot?" and is *not*
        cleared: a single solved CAPTCHA does not retroactively legitimise the
        previous N sends, and clearing it would hand an attacker a fresh batch
        of free sends per solve (10x weaker). It expires on its own after
        ``CAPTCHA_EMAIL_WINDOW``. The UX cost is one CAPTCHA per send for hosts
        that have tripped the IP threshold — acceptable at the configured
        threshold of 10/hour.
        """
        try:
            self.client.delete(self._addr_key(email))
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("captcha gate: clear failed: %s", exc)

    # -- internals -------------------------------------------------------- #
    def _count(self, key: str) -> int:
        try:
            return int(self.client.get(key) or 0)
        except Exception as exc:  # noqa: BLE001 — degrade to "not required"
            logger.warning("captcha gate: read failed, gate degraded: %s", exc)
            return 0

    def _bump(self, key: str) -> None:
        try:
            count = self.client.incr(key)
            if count == 1:
                self.client.expire(key, self._window())
        except Exception as exc:  # noqa: BLE001 — never break sending over counting
            logger.warning("captcha gate: increment failed: %s", exc)


class AuthCodeStore:
    """One-time *authorization code* for the PKCE flow (RFC 7636 / OAuth 2.1).

    Replaces the legacy ``302 redirect_uri#access_token=...`` fragment handoff
    (an OAuth2 Implicit-style flow, deprecated by OAuth 2.1 because it puts
    long-lived tokens — including the refresh token! — into browser history and
    referrers). With PKCE the callback only bounces a harmless single-use code
    via the query string; the SPA then exchanges ``{code, code_verifier}`` for
    the real tokens at ``POST /api/v1/oauth/token/`` over a direct POST that
    never touches the URL bar.

    The code is single-use (``consume`` deletes it) and short-lived (TTL 120s).
    """

    PREFIX = "oauth:code:"
    TTL = 120

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or get_redis()

    def save(
        self,
        *,
        access: str,
        refresh: str,
        token_type: str,
        passport_user_id: str,
        code_challenge: str | None,
        code_challenge_method: str | None,
    ) -> str:
        code = uuid.uuid4().hex + uuid.uuid4().hex[:8]
        payload = json.dumps(
            {
                "access": access,
                "refresh": refresh,
                "token_type": token_type,
                "passport_user_id": passport_user_id,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
            }
        )
        self.client.setex(f"{self.PREFIX}{code}", self.TTL, payload)
        return code

    def consume(self, code: str | None) -> dict[str, Any] | None:
        """Single-use read: returns the token payload and deletes the key."""
        if not code:
            return None
        key = f"{self.PREFIX}{code}"
        raw = self.client.get(key)
        if not raw:
            return None
        self.client.delete(key)
        return json.loads(raw)


# --------------------------------------------------------------------------- #
# PKCE (RFC 7636) helpers
# --------------------------------------------------------------------------- #
def pkce_s256_challenge(verifier: str) -> str:
    """BASE64URL(SHA256(verifier)) without padding — the S256 code challenge."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def pkce_verify(
    challenge: str | None,
    method: str | None,
    verifier: str | None,
) -> bool:
    """True when (verifier, method) matches the stored code_challenge."""
    if not challenge:
        return False
    if not verifier or not isinstance(verifier, str):
        return False
    # RFC 7636 §4.1: verifier is 43..128 chars of [A-Za-z0-9-._~].
    if not (43 <= len(verifier) <= 128):
        return False
    if not re.fullmatch(r"[A-Za-z0-9\-._~]+", verifier):
        return False
    if method in (None, "", "S256", "s256"):
        return pkce_s256_challenge(verifier) == challenge
    if method == "plain":
        return verifier == challenge
    return False


def validate_code_challenge(
    challenge: str | None,
    method: str | None,
) -> tuple[str, str] | None:
    """Validate a (challenge, method) pair from the login query string.

    Returns a normalized ``(challenge, method)`` tuple — ``("", "")`` means
    "PKCE not requested" (legacy fragment mode stays available during the
    migration window) — or ``None`` when the pair is malformed and the login
    attempt must be rejected. Only S256 (default) and plain are accepted.
    """
    if not challenge:
        return ("", "")
    if method in (None, ""):
        method = "S256"
    if method in ("S256", "s256"):
        method = "S256"
    elif method != "plain":
        return None
    # RFC 7636 §4.2: challenge is 43..128 chars of [A-Za-z0-9-._~].
    if not (43 <= len(challenge) <= 128):
        return None
    if not re.fullmatch(r"[A-Za-z0-9\-._~]+", challenge):
        return None
    return (challenge, method)


class GenericLoginTicketStore:
    """One-time ticket for the *provider-agnostic* OAuth entry.

    ``GET /api/v1/oauth/login/`` mints a ticket bound to the integrating
    app's redirect_uri (+ optional PKCE challenge) and hands back a
    passport-web login URL. After the user signs in on the passport web
    (in whichever way they prefer), ``POST /api/v1/oauth/continue/``
    exchanges the ticket — together with the web session's JWT — for a
    single-use authorization code bounced to the app. TTL 600s, single-use.
    """

    PREFIX = "oauth:generic:"
    TTL = 600

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or get_redis()

    def save(
        self,
        *,
        redirect_uri: str,
        code_challenge: str | None,
        code_challenge_method: str | None,
    ) -> str:
        ticket = secrets.token_urlsafe(32)
        payload = json.dumps(
            {
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
            }
        )
        self.client.setex(self.PREFIX + ticket, self.TTL, payload)
        return ticket

    def consume(self, ticket: str) -> dict | None:
        key = self.PREFIX + ticket
        raw = self.client.get(key)
        if not raw:
            return None
        self.client.delete(key)
        try:
            return json.loads(raw)
        except ValueError:
            return None
