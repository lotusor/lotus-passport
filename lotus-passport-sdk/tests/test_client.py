"""PassportClient: verification, attack cases, and the online endpoints."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import jwt as pyjwt
import pytest

from lotus_passport import PassportClient
from lotus_passport.errors import (
    PassportConfigError,
    PassportServiceError,
    TokenExpired,
    TokenInvalid,
    UnknownSigningKey,
)

from .conftest import ISSUER, FakeTransport, KeyPair

USERINFO = "https://passport.test/api/v1/userinfo/"
REFRESH = "https://passport.test/api/v1/token/refresh/"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #
def test_verify_valid_token(client: PassportClient, keypair: KeyPair):
    identity = client.verify_token(keypair.sign())

    assert identity.passport_user_id == "11111111-1111-1111-1111-111111111111"
    assert identity.email == "sdk@lotus.local"
    assert identity.nickname == "sdk-tester"
    assert identity.source == "jwt"
    assert identity.expires_at is not None


def test_verify_is_offline_after_warmup(
    client: PassportClient, keypair: KeyPair, transport: FakeTransport
):
    for _ in range(10):
        client.verify_token(keypair.sign())
    assert transport.jwks_fetches == 1, "verification must not hit the network per request"


def test_default_urls_match_a_stock_deployment():
    c = PassportClient("https://passport.eacm.cn/")  # trailing slash tolerated
    assert c.jwks_url == "https://passport.eacm.cn/.well-known/jwks.json"
    assert c.userinfo_url == "https://passport.eacm.cn/api/v1/userinfo/"
    assert c.refresh_url == "https://passport.eacm.cn/api/v1/token/refresh/"


# --------------------------------------------------------------------------- #
# rejection cases
# --------------------------------------------------------------------------- #
def test_expired_token(client: PassportClient, keypair: KeyPair):
    token = keypair.sign({"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200})
    with pytest.raises(TokenExpired):
        client.verify_token(token)


def test_signature_from_another_key_is_rejected(
    client: PassportClient, rotated_keypair: KeyPair
):
    """Signed with a key that is NOT in our JWKS -> unknown kid, never accepted."""
    with pytest.raises(UnknownSigningKey):
        client.verify_token(rotated_keypair.sign())


def test_key_substitution_is_rejected(
    client: PassportClient, keypair: KeyPair, rotated_keypair: KeyPair
):
    """Attacker signs with their own key but claims our kid — signature must fail."""
    forged = rotated_keypair.sign(kid=keypair.kid)
    with pytest.raises(TokenInvalid):
        client.verify_token(forged)


def test_alg_none_is_rejected(client: PassportClient):
    token = pyjwt.encode(
        {"passport_user_id": "x", "exp": int(time.time()) + 300, "iss": ISSUER},
        key="",
        algorithm="none",
        headers={"kid": "lotus-passport-rsa-1"},
    )
    with pytest.raises(TokenInvalid) as err:
        client.verify_token(token)
    assert "alg" in str(err.value)


def test_hs256_confusion_is_rejected(client: PassportClient, keypair: KeyPair):
    """The classic: sign HS256 using the *public* key as the shared secret.

    Built by hand because PyJWT refuses to *encode* HMAC with a PEM key — but a
    real attacker has no such scruples, so the *verify* side must still say no.
    """
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": keypair.kid}).encode())
    payload = _b64(
        json.dumps(
            {"passport_user_id": "x", "exp": int(time.time()) + 300, "iss": ISSUER}
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    sig = _b64(hmac.new(keypair.public_pem.encode(), signing_input, hashlib.sha256).digest())
    token = f"{header}.{payload}.{sig}"

    with pytest.raises(TokenInvalid):
        client.verify_token(token)


def test_client_refuses_unsafe_algorithms():
    with pytest.raises(PassportConfigError):
        PassportClient("https://passport.test", algorithms=["RS256", "HS256"])
    with pytest.raises(PassportConfigError):
        PassportClient("https://passport.test", algorithms=["none"])


def test_client_requires_base_url():
    with pytest.raises(PassportConfigError):
        PassportClient("")


def test_issuer_mismatch(client: PassportClient, keypair: KeyPair):
    with pytest.raises(TokenInvalid) as err:
        client.verify_token(keypair.sign(issuer="evil-idp"))
    assert "issuer" in str(err.value)


def test_issuer_check_can_be_disabled(transport: FakeTransport, keypair: KeyPair):
    c = PassportClient("https://passport.test", transport=transport, issuer=None)
    assert c.verify_token(keypair.sign(issuer=None)).passport_user_id


def test_audience_is_enforced_when_configured(transport: FakeTransport, keypair: KeyPair):
    c = PassportClient(
        "https://passport.test", transport=transport, issuer=ISSUER, audience="algo-rank"
    )
    assert c.verify_token(keypair.sign({"aud": "algo-rank"})).passport_user_id
    with pytest.raises(TokenInvalid):
        c.verify_token(keypair.sign({"aud": "other-app"}))
    with pytest.raises(TokenInvalid):
        c.verify_token(keypair.sign())  # no aud at all


def test_token_without_exp_is_rejected(client: PassportClient, keypair: KeyPair):
    now = int(time.time())
    token = pyjwt.encode(
        {"passport_user_id": "x", "iat": now, "iss": ISSUER},
        keypair.private_pem,
        algorithm="RS256",
        headers={"kid": keypair.kid},
    )
    with pytest.raises(TokenInvalid):
        client.verify_token(token)


def test_missing_required_claim(client: PassportClient, keypair: KeyPair):
    with pytest.raises(TokenInvalid) as err:
        client.verify_token(keypair.sign({"passport_user_id": ""}))
    assert "passport_user_id" in str(err.value)


def test_garbage_token(client: PassportClient):
    for bad in ["", "not-a-jwt", "a.b.c"]:
        with pytest.raises(TokenInvalid):
            client.verify_token(bad)


def test_clock_skew_leeway(transport: FakeTransport, keypair: KeyPair):
    """A token that expired 10s ago still passes with 30s leeway (skewed clocks)."""
    token = keypair.sign({"exp": int(time.time()) - 10})
    strict = PassportClient(
        "https://passport.test", transport=transport, issuer=ISSUER, leeway=0
    )
    lenient = PassportClient(
        "https://passport.test", transport=transport, issuer=ISSUER, leeway=30
    )
    with pytest.raises(TokenExpired):
        strict.verify_token(token)
    assert lenient.verify_token(token).passport_user_id


# --------------------------------------------------------------------------- #
# header parsing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "header,expected",
    [
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),
        ("BEARER abc", "abc"),
        ("Basic abc", None),
        ("Bearer", None),
        ("Bearer a b", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_bearer(header, expected):
    assert PassportClient.extract_bearer(header) == expected


def test_verify_header(client: PassportClient, keypair: KeyPair):
    assert client.verify_header(f"Bearer {keypair.sign()}").passport_user_id
    with pytest.raises(TokenInvalid):
        client.verify_header("Basic zzz")


# --------------------------------------------------------------------------- #
# online endpoints
# --------------------------------------------------------------------------- #
def test_get_userinfo(client: PassportClient, keypair: KeyPair, transport: FakeTransport):
    transport.routes[USERINFO] = (
        200,
        {
            "passport_user_id": "11111111-1111-1111-1111-111111111111",
            "email": "sdk@lotus.local",
            "nickname": "sdk-tester",
            "avatar": "https://cdn/avatar.png",
            "providers": ["github", "wechat"],
            "is_active": True,
        },
    )
    identity = client.get_userinfo(keypair.sign())

    assert identity.avatar == "https://cdn/avatar.png"
    assert identity.providers == ("github", "wechat")
    assert identity.source == "userinfo"


def test_get_userinfo_verifies_before_spending_a_roundtrip(
    client: PassportClient, rotated_keypair: KeyPair, transport: FakeTransport
):
    with pytest.raises(UnknownSigningKey):
        client.get_userinfo(rotated_keypair.sign())
    assert ("GET", USERINFO) not in transport.calls


def test_get_userinfo_401_is_a_token_error(
    client: PassportClient, keypair: KeyPair, transport: FakeTransport
):
    transport.routes[USERINFO] = (401, {"error": "nope"})
    with pytest.raises(TokenInvalid):
        client.get_userinfo(keypair.sign())


def test_get_userinfo_500_is_a_service_error(
    client: PassportClient, keypair: KeyPair, transport: FakeTransport
):
    transport.routes[USERINFO] = (500, None)
    with pytest.raises(PassportServiceError) as err:
        client.get_userinfo(keypair.sign())
    assert err.value.status_code == 500


def test_refresh(client: PassportClient, transport: FakeTransport):
    transport.post_routes[REFRESH] = (200, {"access": "new-access", "refresh": "new-refresh"})
    pair = client.refresh("old-refresh")

    assert pair.access == "new-access"
    assert pair.refresh == "new-refresh"
    assert transport.last_payload == {"refresh": "old-refresh"}


def test_refresh_rejected(client: PassportClient, transport: FakeTransport):
    transport.post_routes[REFRESH] = (401, {"detail": "token expired"})
    with pytest.raises(TokenInvalid):
        client.refresh("dead-refresh")


def test_refresh_keeps_old_token_when_rotation_is_off(
    client: PassportClient, transport: FakeTransport
):
    transport.post_routes[REFRESH] = (200, {"access": "new-access"})
    assert client.refresh("still-valid").refresh == "still-valid"


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #
def test_discover_adopts_endpoints(client: PassportClient, transport: FakeTransport):
    transport.routes["https://passport.test/.well-known/passport-configuration"] = (
        200,
        {
            "issuer": "lotus-passport",
            "jwks_uri": "https://cdn.test/keys/jwks.json",
            "userinfo_endpoint": "https://passport.test/api/v2/userinfo/",
            "token_refresh_endpoint": "https://passport.test/api/v2/token/refresh/",
        },
    )
    client.discover()

    assert client.jwks_url == "https://cdn.test/keys/jwks.json"
    assert client.jwks.jwks_url == "https://cdn.test/keys/jwks.json"
    assert client.userinfo_url.endswith("/api/v2/userinfo/")


def test_discover_failure_is_a_service_error(client: PassportClient):
    with pytest.raises(PassportServiceError):
        client.discover()
