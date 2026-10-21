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
def test_provider_email_never_hijacks_existing_account(client):
    """provider 回报的邮箱撞上已有账号时：必须新建，绝不能复用（防账号接管）。

    旧行为是「按邮箱合并」，而 GitHub 的公开 email 可以填成任意未验证地址，
    等于任何人都能登录到邮箱真正主人的账号上。合并只能由已登录用户走 bind。
    """
    victim = PassportUser.objects.create(email="u@example.com", nickname="Existing")
    victim.set_password("Str0ng-pass!")
    victim.save()
    before = PassportUser.objects.count()

    r1 = client.get("/api/v1/oauth/github/login/")
    state = parse_qs(urlparse(r1.json()["authorize_url"]).query)["state"][0]
    r2 = client.get(f"/api/v1/oauth/github/callback/?code=abc&state={state}")

    assert r2.status_code == 200
    assert PassportUser.objects.count() == before + 1        # 新建，不是复用
    acc = OAuthAccount.objects.get(provider="github")
    assert acc.user_id != victim.id                          # 挂到了新账号
    assert str(r2.json()["passport_user_id"]) == str(acc.user.passport_id)

    victim.refresh_from_db()
    assert victim.has_usable_password()                      # 没被动过
    assert not OAuthAccount.objects.filter(user=victim).exists()
    # 已被占用的邮箱不会被搬到新账号上（unique + 不归属自己）
    assert acc.user.email is None
    assert acc.user.nickname == "U"


@pytest.mark.django_db(transaction=True)
def test_unclaimed_provider_email_still_lands_on_new_account(client):
    """本地没人用这个邮箱时，新账号照旧拿到它（只是不再拿它去命中别人）。"""
    r1 = client.get("/api/v1/oauth/github/login/")
    state = parse_qs(urlparse(r1.json()["authorize_url"]).query)["state"][0]
    client.get(f"/api/v1/oauth/github/callback/?code=abc&state={state}")

    acc = OAuthAccount.objects.get(provider="github")
    assert acc.user.email == "u@example.com"
