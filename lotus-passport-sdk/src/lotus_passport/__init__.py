"""Lotus Passport SDK — verify unified-auth JWTs in any Python service.

Quickstart::

    from lotus_passport import PassportClient

    passport = PassportClient("https://passport.eacm.cn")   # module-level, reused
    identity = passport.verify_token(token)                   # offline, no network
    print(identity.passport_user_id)                          # your join key

Framework adapters live in ``lotus_passport.integrations`` (FastAPI, DRF, Flask)
and are imported lazily so the SDK never drags in a web framework you don't use.
"""
from __future__ import annotations

from .client import PassportClient
from .errors import (
    JWKSError,
    PassportConfigError,
    PassportError,
    PassportServiceError,
    TokenError,
    TokenExpired,
    TokenInvalid,
    UnknownSigningKey,
)
from .jwks import JWKSCache
from .transport import RequestsTransport, Transport
from .types import PassportIdentity, TokenPair

__version__ = "1.0.0"

__all__ = [
    "PassportClient",
    "PassportIdentity",
    "TokenPair",
    "JWKSCache",
    "Transport",
    "RequestsTransport",
    "PassportError",
    "PassportConfigError",
    "PassportServiceError",
    "JWKSError",
    "TokenError",
    "TokenExpired",
    "TokenInvalid",
    "UnknownSigningKey",
    "__version__",
]
