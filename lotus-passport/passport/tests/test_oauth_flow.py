"""End-to-end OAuth flow + userinfo contract tests (HTTP mocked at provider)."""
from urllib.parse import parse_qs, urlparse

import pytest
from rest_framework.test import APIClient

from passport.models import OAuthAccount, PassportUser
from passport.providers import Identity


class FakeProvider:
    """Stand-in for any real provider; returns a fixed normalized identity."""

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
    # The login view now refuses to start OAuth unless the provider is configured
    # (is_provider_configured). Give the three stub providers dummy creds so the
    # guard passes and the FakeProvider does the actual exchange.
    from django.conf import settings

    monkeypatch.setattr(
        settings,
        "OAUTH_PROVIDERS",
        {
            name: {"client_id": "stub", "client_secret": "stub"}
            for name in ("github", "wechat", "qq")
        },
    )
    return APIClient()


@pytest.mark.django_db(transaction=True)
def test_full_flow_creates_user_and_issues_jwt(client):
    r1 = client.get("/api/v1/oauth/github/login/")
    assert r1.status_code == 200
    authorize = r1.json()["authorize_url"]
    state = parse_qs(urlparse(authorize).query)["state"][0]

    r2 = client.get(f"/api/v1/oauth/github/callback/?code=abc&state={state}")
    assert r2.status_code == 200
    body = r2.json()

    assert "access" in body and "passport_user_id" in body
    user = PassportUser.objects.get(email="u@example.com")
    assert str(user.passport_id) == body["passport_user_id"]

    acc = OAuthAccount.objects.get(user=user, provider="github")
    assert acc.access_token == "at-123"   # stored AES-encrypted, transparent here
    assert acc.refresh_token == "rt-123"


@pytest.mark.django_db(transaction=True)
def test_userinfo_returns_identity_behind_jwt(client):
    r1 = client.get("/api/v1/oauth/github/login/")
    state = parse_qs(urlparse(r1.json()["authorize_url"]).query)["state"][0]
    r2 = client.get(f"/api/v1/oauth/github/callback/?code=abc&state={state}")
    token = r2.json()["access"]

    r3 = client.get("/api/v1/userinfo/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert r3.status_code == 200
    data = r3.json()
    assert data["passport_user_id"]
    assert data["email"] == "u@example.com"
    assert data["providers"] == ["github"]


@pytest.mark.django_db(transaction=True)
def test_callback_with_unknown_state_is_rejected(client):
    r = client.get("/api/v1/oauth/github/callback/?code=x&state=does-not-exist")
    assert r.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_login_unknown_provider_is_rejected(client):
    r = client.get("/api/v1/oauth/unknown/login/")
    assert r.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_existing_email_is_merged_not_duplicated(client):
    PassportUser.objects.create(email="u@example.com", nickname="Existing")
    before = PassportUser.objects.count()

    r1 = client.get("/api/v1/oauth/github/login/")
    state = parse_qs(urlparse(r1.json()["authorize_url"]).query)["state"][0]
    client.get(f"/api/v1/oauth/github/callback/?code=abc&state={state}")

    assert PassportUser.objects.count() == before  # no new user, just a link
    assert OAuthAccount.objects.filter(provider="github").count() == 1
