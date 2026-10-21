"""Tests for OAuth account binding / unbinding / listing (§9.2, GitHub).

The GitHub provider's network calls (token exchange + userinfo) are mocked so
the bind/unbind/accounts flows can be exercised end-to-end without real
credentials. Rate limiting is disabled in these tests to keep them deterministic.
"""
from urllib.parse import parse_qs, urlparse

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from passport.models import OAuthAccount, PassportUser
from passport.providers import GitHubProvider, Identity

FAKE_GH_ID = "gh-123"


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _make_user(email="o@x.com"):
    return PassportUser.objects.create_user(email=email)


@pytest.fixture(autouse=True)
def _no_ratelimit(monkeypatch):
    # Rate limiting hits a shared fakeredis counter; disable so tests stay stable.
    monkeypatch.setattr("passport.views.check_rate_limit", lambda *a, **k: True)


@pytest.fixture
def github(monkeypatch):
    """Configure GitHub as a provider and stub its network calls."""
    monkeypatch.setitem(
        settings.OAUTH_PROVIDERS,
        "github",
        {"client_id": "x", "client_secret": "y"},
    )
    monkeypatch.setattr(
        GitHubProvider,
        "exchange_code",
        lambda self, code: ({"access_token": "at", "refresh_token": "rt", "expires_in": 3600}, None),
    )
    monkeypatch.setattr(
        GitHubProvider,
        "fetch_identity",
        lambda self, raw: Identity(
            provider_user_id=FAKE_GH_ID, email="gh@x.com", nickname="ghuser", avatar=""
        ),
    )
    return FAKE_GH_ID


def _state_from_authorize(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


# -- list ---------------------------------------------------------------- #
@pytest.mark.django_db
def test_accounts_empty(github):
    user = _make_user()
    resp = _client_for(user).get("/api/v1/oauth/accounts/")
    assert resp.status_code == 200
    assert resp.json()["accounts"] == []


@pytest.mark.django_db
def test_accounts_returns_rows(github):
    user = _make_user()
    OAuthAccount.objects.create(user=user, provider="github", provider_user_id=FAKE_GH_ID)
    resp = _client_for(user).get("/api/v1/oauth/accounts/")
    rows = resp.json()["accounts"]
    assert len(rows) == 1
    assert rows[0]["provider"] == "github"
    assert rows[0]["label"] == "GitHub"
    assert "linked_at" in rows[0]


# -- bind: auth + config guards ------------------------------------------ #
@pytest.mark.django_db
def test_bind_requires_auth(github):
    resp = APIClient().post("/api/v1/oauth/github/bind/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_bind_unconfigured_provider(github):
    # Only GitHub is configured in the fixture; WeChat should 400.
    user = _make_user("w@x.com")
    resp = _client_for(user).post("/api/v1/oauth/wechat/bind/")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_bind_already_bound(github):
    user = _make_user()
    OAuthAccount.objects.create(user=user, provider="github", provider_user_id=FAKE_GH_ID)
    resp = _client_for(user).post("/api/v1/oauth/github/bind/")
    assert resp.status_code == 409


# -- bind: full round-trip (init -> callback attaches) ------------------- #
@pytest.mark.django_db
def test_bind_roundtrip(github):
    user = _make_user()
    client = _client_for(user)
    resp = client.post("/api/v1/oauth/github/bind/")
    assert resp.status_code == 200, resp.json()
    state = _state_from_authorize(resp.json()["authorize_url"])

    cb = APIClient()  # callback is a public endpoint
    resp2 = cb.get(f"/api/v1/oauth/github/callback/?code=abc&state={state}")
    assert resp2.status_code == 200, resp2.json()
    assert resp2.json()["status"] == "bound"
    assert OAuthAccount.objects.filter(user=user, provider="github").count() == 1


@pytest.mark.django_db
def test_bind_conflict_other_user(github):
    owner = _make_user("owner@x.com")
    OAuthAccount.objects.create(user=owner, provider="github", provider_user_id=FAKE_GH_ID)
    intruder = _make_user("intruder@x.com")
    client = _client_for(intruder)
    state = _state_from_authorize(
        client.post("/api/v1/oauth/github/bind/").json()["authorize_url"]
    )
    cb = APIClient()
    resp = cb.get(f"/api/v1/oauth/github/callback/?code=abc&state={state}")
    assert resp.status_code == 409
    # intruder must NOT have gained the link
    assert OAuthAccount.objects.filter(user=intruder, provider="github").count() == 0


# -- unbind -------------------------------------------------------------- #
@pytest.mark.django_db
def test_unbind_removes_when_password_present(github):
    user = _make_user()
    user.set_password("secret123")
    user.save()
    OAuthAccount.objects.create(user=user, provider="github", provider_user_id=FAKE_GH_ID)
    resp = _client_for(user).delete("/api/v1/oauth/github/")
    assert resp.status_code == 204
    assert OAuthAccount.objects.filter(user=user, provider="github").count() == 0


@pytest.mark.django_db
def test_unbind_rejected_when_last_method(github):
    # OAuth-only account: no password, no passkey, no other provider.
    user = _make_user()
    OAuthAccount.objects.create(user=user, provider="github", provider_user_id=FAKE_GH_ID)
    resp = _client_for(user).delete("/api/v1/oauth/github/")
    assert resp.status_code == 409


@pytest.mark.django_db
def test_unbind_not_bound(github):
    user = _make_user()
    resp = _client_for(user).delete("/api/v1/oauth/github/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_unbind_requires_auth(github):
    resp = APIClient().delete("/api/v1/oauth/github/")
    assert resp.status_code == 401


# -- login callback still creates a user + issues tokens (non-link branch) #
@pytest.mark.django_db
def test_login_callback_creates_user(github):
    cb = APIClient()
    init = cb.get("/api/v1/oauth/github/login/")
    assert init.status_code == 200, init.json()
    state = _state_from_authorize(init.json()["authorize_url"])
    resp = cb.get(f"/api/v1/oauth/github/callback/?code=abc&state={state}")
    assert resp.status_code == 200, resp.json()
    assert "access" in resp.json()
    assert OAuthAccount.objects.filter(provider="github", provider_user_id=FAKE_GH_ID).count() == 1
