"""Test fixtures — everything runs offline.

No server, no sockets, no network. We generate our own RSA keypair, publish it
through a stub transport as a JWKS document, and mint tokens with it. That means
the suite is deterministic and can prove negative cases (unknown kid, rotated
key, dead passport) that would be painful to reproduce against a live service.
"""
from __future__ import annotations

import base64
import time
from typing import Any

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

DEFAULT_KID = "lotus-passport-rsa-1"
ISSUER = "lotus-passport"


def _b64url_uint(value: int) -> str:
    length = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).decode().rstrip("=")


class KeyPair:
    """An RSA keypair plus its JWKS representation."""

    def __init__(self, kid: str) -> None:
        self.kid = kid
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private_pem = self._key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        self.public_pem = (
            self._key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )

    def jwk(self) -> dict[str, Any]:
        numbers = self._key.public_key().public_numbers()
        return {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": self.kid,
            "n": _b64url_uint(numbers.n),
            "e": _b64url_uint(numbers.e),
        }

    def sign(
        self,
        claims: dict[str, Any] | None = None,
        *,
        kid: str | None = "__self__",
        alg: str = "RS256",
        ttl: int = 300,
        issuer: str | None = ISSUER,
    ) -> str:
        now = int(time.time())
        payload = {
            "token_type": "access",
            "user_id": "1",
            "passport_user_id": "11111111-1111-1111-1111-111111111111",
            "email": "sdk@lotus.local",
            "nickname": "sdk-tester",
            "iat": now,
            "exp": now + ttl,
            "jti": "test-jti",
        }
        if issuer:
            payload["iss"] = issuer
        payload.update(claims or {})
        headers = {}
        header_kid = self.kid if kid == "__self__" else kid
        if header_kid:
            headers["kid"] = header_kid
        return pyjwt.encode(payload, self.private_pem, algorithm=alg, headers=headers or None)


class FakeTransport:
    """Scriptable stand-in for the HTTP layer.

    Records every call so tests can assert on *how many* JWKS fetches happened —
    caching bugs are invisible otherwise.
    """

    def __init__(self, jwks: dict[str, Any] | None = None) -> None:
        self.jwks_response: tuple[int, Any] = (200, jwks or {"keys": []})
        self.routes: dict[str, tuple[int, Any]] = {}
        self.post_routes: dict[str, tuple[int, Any]] = {}
        self.calls: list[tuple[str, str]] = []
        self.jwks_fetches = 0
        self.fail_next_jwks = False

    # -- Transport protocol ------------------------------------------------ #
    def get_json(
        self, url: str, *, headers: dict[str, str] | None = None, timeout: float = 5.0
    ) -> tuple[int, Any]:
        self.calls.append(("GET", url))
        if url.endswith("jwks.json"):
            self.jwks_fetches += 1
            if self.fail_next_jwks:
                self.fail_next_jwks = False
                raise ConnectionError("passport unreachable")
            return self.jwks_response
        if url in self.routes:
            return self.routes[url]
        return 404, {"error": "not found"}

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
    ) -> tuple[int, Any]:
        self.calls.append(("POST", url))
        self.last_payload = payload
        return self.post_routes.get(url, (404, {"error": "not found"}))


@pytest.fixture(scope="session")
def keypair() -> KeyPair:
    """Primary signing key (RSA generation is slow — share it across the suite)."""
    return KeyPair(DEFAULT_KID)


@pytest.fixture(scope="session")
def rotated_keypair() -> KeyPair:
    """A second key, used to simulate rotation and foreign-issuer signatures."""
    return KeyPair("lotus-passport-rsa-2")


@pytest.fixture
def transport(keypair: KeyPair) -> FakeTransport:
    return FakeTransport({"keys": [keypair.jwk()]})


@pytest.fixture
def client(transport: FakeTransport):
    from lotus_passport import PassportClient

    return PassportClient(
        "https://passport.test",
        transport=transport,
        issuer=ISSUER,
        min_refresh_interval=0.0,  # most tests want rotation to be observable
    )
