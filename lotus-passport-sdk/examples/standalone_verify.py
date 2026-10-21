"""Offline smoke test: verify a locally-minted RS256 token with the SDK.

This needs NO running passport server. It uses an in-memory transport so the SDK
pulls its "JWKS" and "userinfo" from Python objects instead of HTTP. That makes it
ideal for:

- A quick "does the SDK work at all?" check in a new repo.
- CI: pin a known keypair, mint a token, assert verification passes.
- Learning the data flow without standing up the full auth center.

It also shows the two verification modes:
- ``verify_token`` — offline, signature-only (fast, no network).
- ``get_userinfo`` — offline-verify THEN a live /userinfo call for avatar+providers.

Run (from the repo root):

    uv run python examples/standalone_verify.py
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from lotus_passport import PassportClient
from lotus_passport.errors import TokenExpired
from lotus_passport.transport import Transport


# --------------------------------------------------------------------------- #
# 1. Generate an RSA-2048 keypair (in real life this lives only in passport).
# --------------------------------------------------------------------------- #
def _int_to_b64url(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    raw = value.to_bytes(length, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def make_keypair() -> tuple[Any, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "dev-key-1",
        "n": _int_to_b64url(pub.n),
        "e": _int_to_b64url(pub.e),
    }
    return private_key, jwk


# --------------------------------------------------------------------------- #
# 2. An in-memory transport: serves JWKS + userinfo without a socket.
# --------------------------------------------------------------------------- #
class InMemoryTransport:
    """Implements the ``lotus_passport.transport.Transport`` protocol.

    The SDK only needs ``get_json`` / ``post_json`` returning ``(status, body)``.
    Swap this for ``requests`` in production.
    """

    def __init__(self, jwks: dict[str, Any], userinfo: dict[str, Any]) -> None:
        self._jwks = jwks
        self._userinfo = userinfo

    def get_json(self, url, *, headers=None, timeout=5.0):
        if url.endswith("/.well-known/jwks.json"):
            return 200, self._jwks
        if url.endswith("/api/v1/userinfo/"):
            # The SDK already verified the token offline before calling this, but
            # a real passport would re-check it; we just return the profile.
            return 200, self._userinfo
        return 404, None

    def post_json(self, url, payload, *, headers=None, timeout=5.0):
        return 404, None


def main() -> None:
    private_key, public_jwk = make_keypair()

    jwks_document = {
        "keys": [public_jwk],
        "issuer": "lotus-passport",
    }
    userinfo = {
        "passport_user_id": "00000000-0000-0000-0000-000000000001",
        "email": "dev@example.com",
        "nickname": "Dev User",
        "avatar": "https://cdn.example.com/avatars/dev.png",
        "providers": ["github", "wechat"],
    }

    client = PassportClient(
        "https://passport.eacm.cn",
        transport=InMemoryTransport(jwks_document, userinfo),
    )

    # Mint a token exactly as passport would (header carries the signing kid).
    # Real passport access tokens always carry exp/iat; the SDK REQUIRES exp.
    now = int(time.time())
    token = jwt.encode(
        {
            "passport_user_id": userinfo["passport_user_id"],
            "email": userinfo["email"],
            "nickname": userinfo["nickname"],
            "iss": "lotus-passport",
            "iat": now,
            "exp": now + 3600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": public_jwk["kid"]},
    )

    # --- offline verification (no network) ---
    identity = client.verify_token(token)
    print("verify_token ->", identity.passport_user_id, identity.email, identity.source)
    assert identity.source == "jwt"

    # --- online resolution (verifies, then enriches via /userinfo) ---
    full = client.get_userinfo(token)
    print("get_userinfo ->", full.avatar, list(full.providers), full.source)
    assert full.source == "userinfo"
    assert full.avatar == userinfo["avatar"]

    # --- failure mode: an expired token is a TokenExpired, not a 500 ---
    expired = jwt.encode(
        {
            "passport_user_id": userinfo["passport_user_id"],
            "iss": "lotus-passport",
            "exp": 1,  # 1970-01-01 -> long expired
        },
        private_key,
        algorithm="RS256",
        headers={"kid": public_jwk["kid"]},
    )
    try:
        client.verify_token(expired)
        raise AssertionError("expired token should have been rejected")
    except TokenExpired:
        print("expired token correctly rejected as TokenExpired")

    print("\nAll offline checks passed. The SDK verifies RS256 tokens correctly.")


if __name__ == "__main__":
    main()
