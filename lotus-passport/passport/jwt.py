"""
JWT issuance for Lotus Passport.

We use djangorestframework-simplejwt. The key claim for integrators is
``passport_user_id`` — a stable UUID that downstream apps (algo_rank, future
projects) use to associate their local accounts with this identity.

Passport intentionally issues ONLY identity claims. Business attributes
(school, roles, scoring) must be resolved by the integrating app.

RS256 signing + ``kid`` header: simplejwt 5.x has no ``TOKEN_BACKEND`` setting,
so we subclass the token classes and inject the JWKS ``kid`` into the protected
header at sign time. Verification uses the public key published at
``/.well-known/jwks.json``.
"""
from __future__ import annotations

import uuid

import jwt as pyjwt
from typing import Any

from django.conf import settings
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import PassportUser


def _sign_with_kid(token: "AccessToken | RefreshToken") -> str:
    """Encode a token, stamping the JWKS ``kid`` into the protected header.

    Mirrors ``TokenBackend.encode`` (audience/issuer handling) but forwards a
    ``kid`` header to PyJWT so integrators can pin the exact JWKS key.
    """
    backend = token.get_token_backend()
    payload = token.payload.copy()
    if backend.audience is not None:
        payload["aud"] = backend.audience
    if backend.issuer is not None:
        payload["iss"] = backend.issuer

    headers: dict[str, Any] = {}
    kid = getattr(settings, "JWT_KID", None)
    if kid:
        headers["kid"] = kid

    encoded = pyjwt.encode(
        payload,
        backend.prepared_signing_key,
        algorithm=backend.algorithm,
        headers=headers or None,
        json_encoder=backend.json_encoder,
    )
    if isinstance(encoded, bytes):
        return encoded.decode("utf-8")
    return encoded


class PassportAccessToken(AccessToken):
    """AccessToken that stamps the JWKS ``kid`` into its header."""

    def __str__(self) -> str:  # noqa: D105
        return _sign_with_kid(self)


class PassportRefreshToken(RefreshToken):
    """RefreshToken that stamps the JWKS ``kid`` into its header."""

    access_token_class = PassportAccessToken

    def __str__(self) -> str:  # noqa: D105
        return _sign_with_kid(self)


class PassportTokenBackend(TokenBackend):
    """Token backend that verifies RS256 tokens by the ``kid`` header.

    simplejwt's stock backend verifies against a single hard-coded
    ``VERIFYING_KEY``. For key rotation we must accept tokens signed by any
    still-valid key, selected by ``kid`` from our ``KeyStore``. HS256 keeps
    using the shared signing key.

    Wired in via ``passport/apps.py`` ``ready()`` (simplejwt has no
    TOKEN_BACKEND setting in 5.x, so the global ``state.token_backend`` is
    replaced there).
    """

    def get_verifying_key(self, token):  # type: ignore[override]
        if self.algorithm.startswith("HS"):
            return self.prepared_signing_key
        if self.jwks_client:
            try:
                return self.jwks_client.get_signing_key_from_jwt(token).key
            except Exception:  # noqa: BLE001
                pass
        # RS256: pick the public key by the token's `kid` (rotation support).
        try:
            header = pyjwt.get_unverified_header(str(token))
            kid = header.get("kid")
        except Exception:  # noqa: BLE001
            kid = None
        pem = settings.KEY_STORE.public_pem_for_kid(kid)
        if pem is None:
            # No retained key for this kid — fall back to the CURRENT active key
            # (covers legacy tokens without a `kid`). A pruned/unknown kid then
            # fails the signature check rather than silently verifying.
            pem = settings.KEY_STORE.active_public_pem
        return self._prepare_key(pem)


def issue_tokens(user: PassportUser) -> dict[str, Any]:
    """Return access + refresh tokens (and the public id) for a user.

    A single ``jti`` is stamped on BOTH tokens so that revoking either one
    (via the server-side blacklist) invalidates the whole session. See
    ``passport.revocation``.
    """
    refresh = PassportRefreshToken.for_user(user)
    jti = uuid.uuid4().hex
    refresh["jti"] = jti
    refresh["passport_user_id"] = user.passport_user_id
    refresh["email"] = user.email or ""
    refresh["nickname"] = user.nickname or ""
    access = refresh.access_token
    access["jti"] = jti
    return {
        "access": str(access),
        "refresh": str(refresh),
        "passport_user_id": user.passport_user_id,
        "token_type": "Bearer",
        "jti": jti,
    }


def decode_access(token: str) -> dict[str, Any]:
    """Validate and return the claims of an access token."""
    return AccessToken(token).payload
