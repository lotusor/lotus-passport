"""Validate the REAL provider wiring end-to-end.

Unlike ``test_oauth_flow`` (which monkeypatches ``get_provider`` with a
``FakeProvider``), this suite drives the actual GitHub / WeChat / QQ provider
classes through the real ``settings.OAUTH_PROVIDERS`` lookup, mocking ONLY the
outbound HTTP calls. It proves that supplying client credentials via settings
makes the full login → callback → consent → JWT loop work against the real
provider code, and that missing credentials fail fast with a 400.

外部应用（非护照第一方 origin）的回调不再直接把 token 弹给应用，而是先 302 到
``OAUTH_CONSENT_PAGE_BASE?ticket=...`` 的授权确认页，用户 allow 后由
``POST /api/v1/oauth/consent/`` 消费票据再 fragment 回跳 —— 测试按这条真实链路走。
"""
from unittest.mock import patch

from urllib.parse import parse_qs, urlparse

import pytest
from rest_framework.test import APIClient

from django.core.cache import cache
from django.test.utils import override_settings

from passport import providers as prov_module
from passport.providers import Identity

REAL_CREDS = {
    "github": {"client_id": "cfg-gh-id", "client_secret": "cfg-gh-secret"},
    "wechat": {"client_id": "cfg-wx-id", "client_secret": "cfg-wx-secret"},
    "qq": {"client_id": "cfg-qq-id", "client_secret": "cfg-qq-secret"},
}

REDIRECT_BASE = "http://testserver/api/v1/oauth"
SPA_CALLBACK = "http://localhost:3000/auth/callback"


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """consent / callback 都挂了按 IP 的限流，同进程连跑多条会互相吃额度。"""
    cache.clear()
    yield
    cache.clear()


def _fake_exchange(self, code):
    # Mirror the real provider return shape: (raw_token, expires_at)
    return {"access_token": f"at-{self.name}", "expires_in": 3600}, None


def _fake_identity(self, raw_token):
    return Identity(
        provider_user_id=f"pid-{self.name}",
        email=f"user@{self.name}.com",
        nickname=f"User_{self.name}",
        avatar="https://a/av.png",
    )


def _consent_ticket(location: str) -> str:
    parsed = urlparse(location)
    assert "oauth/consent" in parsed.path, f"未跳到授权确认页: {location}"
    return parse_qs(parsed.query)["ticket"][0]


def _approve(configured, ticket: str) -> str:
    """在确认页点「允许」，返回后端 302 的最终 Location（带 fragment）。"""
    r = configured.post("/api/v1/oauth/consent/", {"ticket": ticket, "decision": "allow"},
                        format="json")
    assert r.status_code == 302, r.content
    return r["Location"]


@pytest.fixture
def configured(monkeypatch):
    """Patch only the provider's external HTTP calls; keep real classes + config."""
    for cls in (prov_module.GitHubProvider, prov_module.WeChatProvider, prov_module.QQProvider):
        monkeypatch.setattr(cls, "exchange_code", _fake_exchange)
        monkeypatch.setattr(cls, "fetch_identity", _fake_identity)
    return APIClient()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("provider", ["github", "wechat", "qq"])
def test_real_provider_full_flow_issues_jwt_in_fragment(configured, provider):
    with override_settings(
        OAUTH_PROVIDERS=REAL_CREDS,
        PASSPORT_OAUTH_REDIRECT_BASE=REDIRECT_BASE,
        FRONTEND_SUCCESS_REDIRECT="http://localhost:3000/",
    ):
        r1 = configured.get(f"/api/v1/oauth/{provider}/login/?redirect_uri={SPA_CALLBACK}")
        assert r1.status_code == 200
        authorize = r1.json()["authorize_url"]
        q = parse_qs(urlparse(authorize).query)

        # 1) authorize URL carries the REAL client_id pulled from settings
        assert q["client_id"][0] == REAL_CREDS[provider]["client_id"]
        # 2) provider is told to call back to OUR backend, not the SPA directly.
        # QQ 互联校验器拒绝尾部斜杠，故 qq 发出的回调不带 "/"。
        suffix = "" if provider == "qq" else "/"
        assert q["redirect_uri"][0] == f"{REDIRECT_BASE}/{provider}/callback{suffix}"
        # 3) CSRF state is present
        assert q["state"][0]

        state = q["state"][0]
        # Provider redirects back to us with code + state
        r2 = configured.get(
            f"/api/v1/oauth/{provider}/callback/?code=xyz&state={state}"
        )
        assert r2.status_code == 302, r2.content
        # 4) 外部应用要先过授权确认页，令牌此刻还不在 Location 里
        ticket = _consent_ticket(r2["Location"])

        loc = _approve(configured, ticket)
        # 5) 用户放行后才把令牌以 fragment 弹回应用回调
        assert loc.startswith(SPA_CALLBACK + "#")
        frag = parse_qs(urlparse(loc).fragment)
        assert frag["access_token"][0]
        assert frag["passport_user_id"][0]


@pytest.mark.django_db(transaction=True)
def test_first_party_redirect_skips_consent_screen(configured):
    """护照自己的 SPA 属第一方：不插授权确认页，回调直接带 fragment 回跳。"""
    with override_settings(
        OAUTH_PROVIDERS=REAL_CREDS,
        PASSPORT_OAUTH_REDIRECT_BASE=REDIRECT_BASE,
        OAUTH_FIRST_PARTY_ORIGINS=["http://localhost:3000"],
    ):
        r1 = configured.get(f"/api/v1/oauth/github/login/?redirect_uri={SPA_CALLBACK}")
        state = parse_qs(urlparse(r1.json()["authorize_url"]).query)["state"][0]
        r2 = configured.get(f"/api/v1/oauth/github/callback/?code=xyz&state={state}")
        assert r2.status_code == 302, r2.content
        assert r2["Location"].startswith(SPA_CALLBACK + "#"), r2["Location"]


@pytest.mark.django_db(transaction=True)
def test_consent_denied_returns_error_marker(configured):
    """用户在确认页点「拒绝」：不签发回应用域的令牌，带 oauth_error 回跳。"""
    with override_settings(
        OAUTH_PROVIDERS=REAL_CREDS,
        PASSPORT_OAUTH_REDIRECT_BASE=REDIRECT_BASE,
    ):
        r1 = configured.get(f"/api/v1/oauth/github/login/?redirect_uri={SPA_CALLBACK}")
        state = parse_qs(urlparse(r1.json()["authorize_url"]).query)["state"][0]
        r2 = configured.get(f"/api/v1/oauth/github/callback/?code=xyz&state={state}")
        ticket = _consent_ticket(r2["Location"])
        r3 = configured.post("/api/v1/oauth/consent/",
                             {"ticket": ticket, "decision": "deny"}, format="json")
        assert r3.status_code == 302
        assert "oauth_error=access_denied" in r3["Location"]
        # 票据一次性：同一张票不能再被消费
        r4 = configured.post("/api/v1/oauth/consent/",
                             {"ticket": ticket, "decision": "allow"}, format="json")
        assert r4.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_userinfo_resolves_identity_after_real_flow(configured):
    with override_settings(
        OAUTH_PROVIDERS=REAL_CREDS,
        PASSPORT_OAUTH_REDIRECT_BASE=REDIRECT_BASE,
        FRONTEND_SUCCESS_REDIRECT="http://localhost:3000/",
    ):
        r1 = configured.get(f"/api/v1/oauth/github/login/?redirect_uri={SPA_CALLBACK}")
        state = parse_qs(urlparse(r1.json()["authorize_url"]).query)["state"][0]
        r2 = configured.get(f"/api/v1/oauth/github/callback/?code=xyz&state={state}")
        loc = _approve(configured, _consent_ticket(r2["Location"]))
        access = parse_qs(urlparse(loc).fragment)["access_token"][0]

        r3 = configured.get("/api/v1/userinfo/", HTTP_AUTHORIZATION=f"Bearer {access}")
        assert r3.status_code == 200
        data = r3.json()
        assert data["email"] == "user@github.com"
        assert data["providers"] == ["github"]


@pytest.mark.django_db(transaction=True)
def test_login_without_credentials_fails_fast():
    # No creds → clear 400, not a redirect to the provider with a bogus id.
    # 文案对用户是「当前功能开发中」（不把哪个 provider 没配好暴露给未登录访客），
    # 这里锁的是行为：400 + 绝不返回一个带假 client_id 的 authorize_url。
    with override_settings(
        OAUTH_PROVIDERS={"github": {"client_id": "", "client_secret": ""}}
    ):
        r = APIClient().get("/api/v1/oauth/github/login/")
        assert r.status_code == 400
        body = r.json()
        assert body["error"]["message"]
        assert "authorize_url" not in body
