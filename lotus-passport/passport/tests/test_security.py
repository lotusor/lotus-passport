"""Security hardening tests: OAuth redirect_uri allow-list + token revocation."""
from urllib.parse import parse_qs, urlparse

import pytest
from rest_framework.test import APIClient

from passport.providers import Identity


class FakeProvider:
    name = "github"

    def get_authorize_url(self, state: str) -> str:
        return f"https://github.com/login?state={state}"

    def exchange_code(self, code: str):
        return {"access_token": "at-123", "refresh_token": "rt-123", "expires_in": 3600}, None

    def fetch_identity(self, raw_token):
        return Identity(
            provider_user_id="gh-99",
            email="u@example.com",
            nickname="U",
            avatar="https://a/av.png",
        )


@pytest.fixture
def client(monkeypatch):
    def _fake(provider, redirect_uri=None):
        if provider in ("github", "wechat", "qq"):
            return FakeProvider()
        return None

    monkeypatch.setattr("passport.views.get_provider", _fake)
    from django.conf import settings

    monkeypatch.setattr(
        settings,
        "OAUTH_PROVIDERS",
        {name: {"client_id": "stub", "client_secret": "stub"} for name in ("github", "wechat", "qq")},
    )
    return APIClient()


def _login_state(client, redirect_uri=""):
    url = "/api/v1/oauth/github/login/"
    if redirect_uri:
        url += f"?redirect_uri={redirect_uri}"
    r = client.get(url)
    assert r.status_code == 200, r.content
    return parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]


# --------------------------------------------------------------------------- #
# redirect_uri allow-list (A-11)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db(transaction=True)
def test_login_rejects_disallowed_redirect_uri(client):
    r = client.get("/api/v1/oauth/github/login/?redirect_uri=https://evil.example.com/phish")
    assert r.status_code == 400
    assert "redirect_uri" in r.json()["error"]["message"]


@pytest.mark.django_db(transaction=True)
def test_login_allows_localhost_redirect_uri_in_testing(client):
    # localhost is auto-allowed under DEBUG/TESTING (mirrors CORS behaviour).
    state = _login_state(client, "http://localhost:3000/auth/callback")
    assert state


@pytest.mark.django_db(transaction=True)
def test_callback_ignores_injected_redirect_uri(client):
    # Login stored an EMPTY redirect_uri. An attacker-supplied ?redirect_uri on
    # the callback must NOT be honoured — the view only trusts the state-stored
    # value, so it falls back to a JSON response rather than redirecting.
    state = _login_state(client)
    r = client.get(
        f"/api/v1/oauth/github/callback/?code=abc&state={state}"
        "&redirect_uri=https://evil.example.com/phish"
    )
    assert r.status_code == 200
    assert "access" in r.json()  # tokens returned as JSON, not redirected to evil


@pytest.mark.django_db(transaction=True)
def test_callback_honours_state_stored_redirect_uri(client):
    state = _login_state(client, "http://localhost:3000/auth/callback")
    r = client.get(f"/api/v1/oauth/github/callback/?code=abc&state={state}")
    assert r.status_code == 302
    location = r.headers.get("Location", "")
    assert location.startswith("http://localhost:3000/auth/callback#")
    assert "access_token" in location


@pytest.mark.django_db(transaction=True)
def test_production_allow_list_enforced(monkeypatch, client):
    from django.conf import settings

    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(
        settings, "OAUTH_ALLOWED_REDIRECT_URIS", ["https://app.example.com"]
    )

    # Allowed origin (any path) -> 200
    r_ok = client.get("/api/v1/oauth/github/login/?redirect_uri=https://app.example.com/cb")
    assert r_ok.status_code == 200

    # Disallowed external host -> 400
    r_bad = client.get("/api/v1/oauth/github/login/?redirect_uri=https://evil.example.com")
    assert r_bad.status_code == 400


# --------------------------------------------------------------------------- #
# Server-side token revocation (logout)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db(transaction=True)
def test_logout_revokes_token_then_userinfo_401(client):
    state = _login_state(client)
    cb = client.get(f"/api/v1/oauth/github/callback/?code=abc&state={state}")
    token = cb.json()["access"]

    # Session valid before logout.
    ok = client.get("/api/v1/userinfo/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert ok.status_code == 200

    # Logout (revoke access jti).
    lo = client.post("/api/v1/logout/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert lo.status_code == 200
    assert lo.json()["revoked"] is True

    # Same token is now rejected.
    dead = client.get("/api/v1/userinfo/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert dead.status_code == 401


@pytest.mark.django_db(transaction=True)
def test_logout_requires_authentication(client):
    r = client.post("/api/v1/logout/")
    assert r.status_code == 401


@pytest.mark.django_db(transaction=True)
def test_logout_is_scoped_per_jti(client):
    # First session.
    s1 = _login_state(client)
    t1 = client.get(f"/api/v1/oauth/github/callback/?code=abc&state={s1}").json()["access"]
    # Second, independent session.
    s2 = _login_state(client)
    t2 = client.get(f"/api/v1/oauth/github/callback/?code=abc&state={s2}").json()["access"]

    client.post("/api/v1/logout/", HTTP_AUTHORIZATION=f"Bearer {t1}")

    # t1 dead, t2 still good.
    assert client.get("/api/v1/userinfo/", HTTP_AUTHORIZATION=f"Bearer {t1}").status_code == 401
    assert client.get("/api/v1/userinfo/", HTTP_AUTHORIZATION=f"Bearer {t2}").status_code == 200


# --------------------------------------------------------------------------- #
# Dev stub must also honour the allow-list
# --------------------------------------------------------------------------- #
@pytest.mark.django_db(transaction=True)
def test_dev_login_rejects_bad_redirect(client):
    r = client.get("/api/v1/dev/login/?redirect_uri=https://evil.example.com")
    assert r.status_code == 400
    assert "redirect_uri" in r.json()["error"]["message"]


@pytest.mark.django_db(transaction=True)
def test_dev_login_allows_localhost_redirect(client):
    r = client.get("/api/v1/dev/login/?redirect_uri=http://localhost:3000/auth/callback")
    assert r.status_code == 302
    assert r.headers.get("Location", "").startswith("http://localhost:3000/auth/callback#")
