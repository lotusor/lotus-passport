"""Tests for the authorization-code + PKCE login flow (RFC 7636).

The full OAuth round-trip is exercised the same way test_oauth_real_config
does it: a real state row, a fake provider exchange, then the new
POST /api/v1/oauth/token/ exchange with the code_verifier.
"""
import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from rest_framework.test import APIClient

from passport.models import PassportUser
from passport.ratelimit import (
    AuthCodeStore,
    OAuthStateStore,
    pkce_s256_challenge,
    pkce_verify,
    validate_code_challenge,
)


VERIFIER = "test-verifier-test-verifier-test-verifier-123456"  # 57 chars, unreserved


def _verifier() -> str:
    return VERIFIER


def _challenge() -> str:
    return pkce_s256_challenge(VERIFIER)


# --- pure helpers ---------------------------------------------------------- #
def test_pkce_s256_roundtrip():
    assert pkce_s256_challenge(VERIFIER) == base64.urlsafe_b64encode(
        hashlib.sha256(VERIFIER.encode()).digest()
    ).decode().rstrip("=")


def test_pkce_verify_matches():
    assert pkce_verify(_challenge(), "S256", VERIFIER) is True
    assert pkce_verify(_challenge(), None, VERIFIER) is True  # default S256
    assert pkce_verify(_challenge(), "S256", "wrong-verifier-wrong-verifier-wrong-123456") is False


def test_pkce_verify_rejects_malformed_verifier():
    assert pkce_verify(_challenge(), "S256", "short") is False  # <43
    assert pkce_verify(_challenge(), "S256", "x" * 200) is False  # >128
    assert pkce_verify(_challenge(), "S256", "包含非法字符" * 20) is False
    assert pkce_verify(_challenge(), "plain", VERIFIER) is False  # method mismatch


def test_validate_code_challenge_normalizes():
    assert validate_code_challenge(None, None) == ("", "")
    assert validate_code_challenge("", "") == ("", "")
    assert validate_code_challenge(_challenge(), None) == (_challenge(), "S256")
    assert validate_code_challenge(_challenge(), "S256") == (_challenge(), "S256")
    assert validate_code_challenge(VERIFIER, "plain") == (VERIFIER, "plain")
    # Malformed -> rejected.
    assert validate_code_challenge("bad challenge!", "S256") is None
    assert validate_code_challenge(_challenge(), "HS256") is None
    assert validate_code_challenge("too-short", "S256") is None


# --- store ------------------------------------------------------------------ #
@pytest.mark.django_db
def test_auth_code_store_single_use():
    store = AuthCodeStore()
    code = store.save(
        access="at", refresh="rt", token_type="Bearer",
        passport_user_id="pid-1", code_challenge=_challenge(),
        code_challenge_method="S256",
    )
    first = store.consume(code)
    assert first["access"] == "at"
    assert store.consume(code) is None  # single use


# --- end-to-end: login -> callback ?code= -> token exchange ------------------ #
@pytest.fixture
def _configured_github(settings, monkeypatch):
    """Fake a configured github provider + stub the code exchange."""
    from passport.providers import Identity

    settings.OAUTH_PROVIDERS = {
        "github": {
            "client_id": "cid",
            "client_secret": "secret",
            "authorize_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "scope": "read:user user:email",
        }
    }
    identity = Identity(
        provider_user_id="gh-pkce-1",
        email="pkce.user@example.com",
        nickname="PKCE 用户",
        avatar="",
    )

    class _Prov:
        def get_authorize_url(self, state):
            return f"https://github.com/login/oauth/authorize?state={state}"

        def exchange_code(self, code):
            return {"access_token": "upstream-at", "refresh_token": None}, None

        def fetch_identity(self, raw):
            return identity

    monkeypatch.setattr("passport.views.get_provider", lambda p: _Prov())
    monkeypatch.setattr("passport.views.is_provider_configured", lambda p: True)


@pytest.mark.django_db
def test_pkce_flow_exchanges_code_for_tokens(_configured_github, settings):
    settings.DEBUG = True
    settings.OAUTH_FIRST_PARTY_ORIGINS = []  # localhost:3000 -> external? keep first-party simple
    settings.OAUTH_FIRST_PARTY_ORIGINS = ["http://localhost:3000"]
    client = APIClient()

    # 1) login with PKCE
    r1 = client.get(
        "/api/v1/oauth/github/login/",
        {
            "redirect_uri": "http://localhost:3000/auth/callback",
            "code_challenge": _challenge(),
            "code_challenge_method": "S256",
        },
    )
    assert r1.status_code == 200
    state = parse_qs(urlparse(r1.json()["authorize_url"]).query)["state"][0]

    # 2) provider callback -> must 302 with ?code= (NOT a #fragment)
    r2 = client.get(
        f"/api/v1/oauth/github/callback/?code=upstream-code&state={state}"
    )
    assert r2.status_code == 302
    loc = r2["Location"]
    assert loc.startswith("http://localhost:3000/auth/callback?code=")
    assert "#" not in loc
    code = parse_qs(urlparse(loc).query)["code"][0]

    # 3) exchange code + verifier for the tokens
    r3 = client.post(
        "/api/v1/oauth/token/",
        {"code": code, "code_verifier": VERIFIER},
        format="json",
    )
    assert r3.status_code == 200
    body = r3.json()
    assert body["access"] and body["refresh"]
    assert body["passport_user_id"]

    # 4) the issued access token carries the aud bound to the redirect origin
    import jwt as pyjwt

    claims = pyjwt.decode(body["access"], options={"verify_signature": False})
    assert claims.get("aud") == "http://localhost:3000"

    # 5) the code is single-use
    r4 = client.post(
        "/api/v1/oauth/token/",
        {"code": code, "code_verifier": VERIFIER},
        format="json",
    )
    assert r4.status_code == 400


@pytest.mark.django_db
def test_pkce_flow_rejects_wrong_verifier(_configured_github, settings):
    settings.DEBUG = True
    settings.OAUTH_FIRST_PARTY_ORIGINS = ["http://localhost:3000"]
    client = APIClient()
    r1 = client.get(
        "/api/v1/oauth/github/login/",
        {
            "redirect_uri": "http://localhost:3000/auth/callback",
            "code_challenge": _challenge(),
        },
    )
    state = parse_qs(urlparse(r1.json()["authorize_url"]).query)["state"][0]
    r2 = client.get(f"/api/v1/oauth/github/callback/?code=c&state={state}")
    code = parse_qs(urlparse(r2["Location"]).query)["code"][0]

    r3 = client.post(
        "/api/v1/oauth/token/",
        {"code": code, "code_verifier": "wrong-verifier-wrong-verifier-wrong-123"},
        format="json",
    )
    assert r3.status_code == 400
    assert "PKCE" in r3.json()["error"]["message"]


@pytest.mark.django_db
def test_login_rejects_malformed_code_challenge(_configured_github, settings):
    settings.DEBUG = True
    client = APIClient()
    r = client.get(
        "/api/v1/oauth/github/login/",
        {
            "redirect_uri": "http://localhost:3000/auth/callback",
            "code_challenge": "bad value!",
        },
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_legacy_fragment_flow_still_works(_configured_github, settings):
    """旧前端（不带 code_challenge）继续走 fragment 回跳（过渡兼容）。"""
    settings.DEBUG = True
    settings.OAUTH_FIRST_PARTY_ORIGINS = ["http://localhost:3000"]
    client = APIClient()
    r1 = client.get(
        "/api/v1/oauth/github/login/",
        {"redirect_uri": "http://localhost:3000/auth/callback"},
    )
    assert r1.status_code == 200
    state = parse_qs(urlparse(r1.json()["authorize_url"]).query)["state"][0]
    r2 = client.get(f"/api/v1/oauth/github/callback/?code=c&state={state}")
    assert r2.status_code == 302
    loc = r2["Location"]
    assert loc.startswith("http://localhost:3000/auth/callback#access_token=")
