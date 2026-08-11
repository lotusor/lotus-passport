"""Exception hierarchy for the Lotus Passport SDK.

Everything derives from :class:`PassportError`, so an integrating app can wrap
the whole SDK in one ``except``. The split that matters in practice:

* :class:`TokenError` -> respond **401**. The caller's credential is bad.
* :class:`JWKSError` / :class:`PassportServiceError` -> respond **503**.
  *We* are broken (passport unreachable, JWKS malformed), not the caller.
  Returning 401 here is a classic mistake: it silently logs every user out
  during a passport outage instead of surfacing a retryable error.
"""
from __future__ import annotations


class PassportError(Exception):
    """Base class for every SDK failure."""


class PassportConfigError(PassportError):
    """The SDK itself is misconfigured (bad base_url, unsafe algorithm, ...)."""


class PassportServiceError(PassportError):
    """Lotus Passport was reachable but returned an unusable response.

    Attributes:
        status_code: HTTP status returned by passport, when there was one.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class JWKSError(PassportServiceError):
    """The JWKS document could not be fetched or parsed."""


class TokenError(PassportError):
    """The presented token is not acceptable. Always maps to HTTP 401."""


class TokenExpired(TokenError):
    """Signature is valid but ``exp`` has passed — the client should refresh."""


class TokenInvalid(TokenError):
    """Malformed, wrong signature, wrong issuer/audience, or unusable header."""


class UnknownSigningKey(TokenInvalid):
    """The token's ``kid`` is not in the JWKS, even after a forced refresh."""


__all__ = [
    "PassportError",
    "PassportConfigError",
    "PassportServiceError",
    "JWKSError",
    "TokenError",
    "TokenExpired",
    "TokenInvalid",
    "UnknownSigningKey",
]
