"""The main entry point: :class:`PassportClient`.

Two ways to authenticate an incoming request, and the choice matters:

``verify_token()`` — **offline**. Checks the RS256 signature against the cached
JWKS public key. Zero network calls on the hot path, works while passport is
down, but the identity is only as fresh as the token (up to ACCESS_TOKEN_LIFETIME
stale, and it cannot see a revocation).

``get_userinfo()`` — **online**. Asks passport who this token belongs to. Always
current, returns avatar + linked providers, but adds a round-trip to every
request and couples your availability to passport's.

Recommended: ``verify_token()`` on every request, ``get_userinfo()`` only on
first sight of a ``passport_user_id`` (to provision the local user row) or when
the user explicitly refreshes their profile.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from .errors import (
    PassportConfigError,
    PassportServiceError,
    TokenExpired,
    TokenInvalid,
)
from .jwks import JWKSCache
from .transport import RequestsTransport, Transport
from .types import PassportIdentity, TokenPair

_DEFAULT_ALGORITHMS: tuple[str, ...] = ("RS256",)
# Symmetric algorithms can never be safe here: the "key" would be the public key
# from the JWKS, which anyone can download and sign with.
_FORBIDDEN_ALGORITHMS = {"none", "HS256", "HS384", "HS512"}


class PassportClient:
    """Verify and resolve Lotus Passport identities.

    Args:
        base_url: Root URL of the passport deployment, e.g.
            ``https://passport.eacm.cn``. Trailing slash optional.
        issuer: Expected ``iss`` claim. Pinning this is what stops a token from
            *some other* RS256 issuer being replayed against your API. Pass
            ``None`` only if your passport predates the ``iss`` claim.
        audience: Expected ``aud``. ``None`` (default) disables the check —
            passport does not currently set an audience.
        algorithms: Accepted signature algorithms. Symmetric ones are rejected.
        leeway: Clock-skew tolerance in seconds applied to ``exp``/``iat``.
        cache_ttl: JWKS cache lifetime in seconds.
        min_refresh_interval: Throttle for unknown-``kid`` forced refreshes.
        timeout: HTTP timeout in seconds.
        transport: Custom :class:`~lotus_passport.transport.Transport`.
        jwks_url / userinfo_url / refresh_url: Override the derived paths.

    Raises:
        PassportConfigError: base_url is missing, or an unsafe algorithm was
            requested.
    """

    def __init__(
        self,
        base_url: str,
        *,
        issuer: str | None = "lotus-passport",
        audience: str | None = None,
        algorithms: Sequence[str] = _DEFAULT_ALGORITHMS,
        leeway: int = 30,
        cache_ttl: float = 600.0,
        min_refresh_interval: float = 30.0,
        timeout: float = 5.0,
        transport: Transport | None = None,
        jwks_url: str | None = None,
        userinfo_url: str | None = None,
        refresh_url: str | None = None,
    ) -> None:
        if not base_url or not base_url.strip():
            raise PassportConfigError("base_url is required, e.g. https://passport.eacm.cn")

        bad = _FORBIDDEN_ALGORITHMS.intersection(algorithms)
        if bad:
            raise PassportConfigError(
                f"Refusing to accept {sorted(bad)}. Lotus Passport signs with RS256; "
                "accepting a symmetric or 'none' algorithm here would let anyone "
                "forge tokens using the public key."
            )
        if not algorithms:
            raise PassportConfigError("algorithms must not be empty")

        self.base_url = base_url.rstrip("/")
        self.issuer = issuer
        self.audience = audience
        self.algorithms = tuple(algorithms)
        self.leeway = leeway
        self.timeout = timeout

        self.jwks_url = jwks_url or f"{self.base_url}/.well-known/jwks.json"
        self.userinfo_url = userinfo_url or f"{self.base_url}/api/v1/userinfo/"
        self.refresh_url = refresh_url or f"{self.base_url}/api/v1/token/refresh/"
        self.configuration_url = f"{self.base_url}/.well-known/passport-configuration"

        self._transport: Transport = transport or RequestsTransport()
        self.jwks = JWKSCache(
            self.jwks_url,
            self._transport,
            ttl=cache_ttl,
            min_refresh_interval=min_refresh_interval,
            timeout=timeout,
        )

    # ------------------------------------------------------------------ #
    # discovery
    # ------------------------------------------------------------------ #
    def discover(self) -> dict[str, Any]:
        """Pull ``/.well-known/passport-configuration`` and adopt its endpoints.

        Optional. Call it once at startup if you would rather not hard-code paths;
        the defaults already match a stock deployment.

        Returns:
            The raw configuration document.

        Raises:
            PassportServiceError: The document is missing or unusable.
        """
        status, body = self._transport.get_json(self.configuration_url, timeout=self.timeout)
        if status != 200 or not isinstance(body, dict):
            raise PassportServiceError(
                f"Discovery failed: {self.configuration_url} returned HTTP {status}",
                status_code=status,
            )
        if body.get("jwks_uri"):
            self.jwks_url = body["jwks_uri"]
            self.jwks.jwks_url = body["jwks_uri"]
            self.jwks.clear()
        if body.get("userinfo_endpoint"):
            self.userinfo_url = body["userinfo_endpoint"]
        if body.get("token_refresh_endpoint"):
            self.refresh_url = body["token_refresh_endpoint"]
        if body.get("issuer") and self.issuer is not None:
            self.issuer = body["issuer"]
        return body

    # ------------------------------------------------------------------ #
    # offline verification
    # ------------------------------------------------------------------ #
    def verify_token(
        self, token: str, *, required_claims: Iterable[str] = ("passport_user_id",)
    ) -> PassportIdentity:
        """Verify an access token offline and return the identity it carries.

        Args:
            token: Raw JWT (no ``Bearer `` prefix — use :meth:`verify_header`).
            required_claims: Claims that must be present and non-empty.

        Returns:
            The verified :class:`~lotus_passport.types.PassportIdentity`.

        Raises:
            TokenExpired: Signature is fine but the token has expired.
            TokenInvalid: Anything else wrong with the token.
            UnknownSigningKey: ``kid`` not published in the JWKS.
            JWKSError: Keys could not be fetched (service problem, not the caller's).
        """
        import jwt as pyjwt

        if not token or not isinstance(token, str):
            raise TokenInvalid("empty token")

        try:
            header = pyjwt.get_unverified_header(token)
        except Exception as exc:  # noqa: BLE001
            raise TokenInvalid(f"malformed token header: {exc}") from exc

        # Pin the algorithm from *our* allow-list, never from the token header —
        # trusting header.alg is the textbook algorithm-confusion vulnerability.
        if header.get("alg") not in self.algorithms:
            raise TokenInvalid(
                f"unexpected alg={header.get('alg')!r}; this client only accepts "
                f"{list(self.algorithms)}"
            )

        key = self.jwks.get_key(header.get("kid"))

        options = {
            "require": ["exp"],
            "verify_aud": self.audience is not None,
        }
        try:
            claims = pyjwt.decode(
                token,
                key,
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway,
                options=options,
            )
        except pyjwt.ExpiredSignatureError as exc:
            raise TokenExpired("access token expired; use the refresh token") from exc
        except pyjwt.InvalidIssuerError as exc:
            raise TokenInvalid(
                f"issuer mismatch: expected {self.issuer!r}"
            ) from exc
        except pyjwt.PyJWTError as exc:
            raise TokenInvalid(f"token rejected: {exc}") from exc

        for claim in required_claims:
            if not claims.get(claim):
                raise TokenInvalid(f"missing required claim: {claim}")

        return PassportIdentity.from_claims(claims)

    def verify_header(self, authorization: str | None) -> PassportIdentity:
        """Verify a raw ``Authorization: Bearer <token>`` header value.

        Raises:
            TokenInvalid: Header missing or not a Bearer scheme.
        """
        token = self.extract_bearer(authorization)
        if token is None:
            raise TokenInvalid("missing or malformed Authorization: Bearer header")
        return self.verify_token(token)

    @staticmethod
    def extract_bearer(authorization: str | None) -> str | None:
        """Pull the token out of an Authorization header, or return ``None``."""
        if not authorization:
            return None
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        return parts[1]

    # ------------------------------------------------------------------ #
    # online calls
    # ------------------------------------------------------------------ #
    def get_userinfo(self, token: str, *, verify_first: bool = True) -> PassportIdentity:
        """Resolve the full profile from passport.

        Args:
            token: Access token.
            verify_first: Verify offline before spending a round-trip. Keep this
                on — it turns "attacker floods us with junk tokens" from a
                passport DoS into a local signature check.

        Returns:
            Identity including ``avatar`` and linked ``providers``.

        Raises:
            TokenInvalid: passport answered 401/403 for this token.
            PassportServiceError: passport is unreachable or returned garbage.
        """
        claims: dict[str, Any] = {}
        if verify_first:
            claims = self.verify_token(token).claims

        status, body = self._transport.get_json(
            self.userinfo_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if status in (401, 403):
            raise TokenInvalid(f"passport rejected the token (HTTP {status})")
        if status != 200 or not isinstance(body, dict):
            raise PassportServiceError(
                f"userinfo failed: HTTP {status} from {self.userinfo_url}",
                status_code=status,
            )
        return PassportIdentity.from_userinfo(body, claims)

    def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a refresh token for a new access token.

        Raises:
            TokenInvalid: The refresh token is expired or bogus.
            PassportServiceError: passport is unreachable or returned garbage.
        """
        status, body = self._transport.post_json(
            self.refresh_url, {"refresh": refresh_token}, timeout=self.timeout
        )
        if status in (400, 401):
            raise TokenInvalid("refresh token rejected; the user must log in again")
        if status != 200 or not isinstance(body, dict) or not body.get("access"):
            raise PassportServiceError(
                f"refresh failed: HTTP {status} from {self.refresh_url}",
                status_code=status,
            )
        return TokenPair(
            access=body["access"],
            refresh=body.get("refresh", refresh_token),
            token_type=body.get("token_type", "Bearer"),
        )


__all__ = ["PassportClient"]
