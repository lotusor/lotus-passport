"""Trusted-device revoke + auto-login trust gate (§9.3).

Covers the two reported defects:
* revoking a device must return 204 (never 500) and log the device out;
* untrusting a device must make its next refresh fail (401) so it re-auths.
"""
import pytest
from rest_framework.test import APIClient

from passport.jwt import issue_tokens
from passport.models import PassportUser, Session, TrustedDevice
from passport.auth_events import parse_user_agent

# 固定 UA，保证「刷新请求的设备指纹」与「TrustedDevice 记录」可精确匹配。
DEVICE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
)


def _auth_client(user: PassportUser) -> tuple[APIClient, dict]:
    tokens = issue_tokens(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    # 必须带 UA：IsAuthenticatedAndTrusted 按 UA 指纹匹配 TrustedDevice。
    client.defaults["HTTP_USER_AGENT"] = DEVICE_UA
    return client, tokens


def _make_device(user: PassportUser, *, trusted: bool, ua: str = DEVICE_UA) -> TrustedDevice:
    p = parse_user_agent(ua)
    return TrustedDevice.objects.create(
        user=user,
        name="Edge · Windows",
        device_type=p["device_type"],
        os=p["os"],
        browser=p["browser"],
        trusted=trusted,
    )


@pytest.mark.django_db
def test_revoke_device_returns_204_and_revokes_sessions():
    user = PassportUser.objects.create(email="revoke@x.com")
    client, tokens = _auth_client(user)
    dev = _make_device(user, trusted=True)
    # 该设备当前有一条活跃会话
    Session.objects.create(
        user=user,
        jti=tokens["jti"],
        device_type=dev.device_type,
        os=dev.os,
        browser=dev.browser,
    )

    resp = client.delete(f"/api/v1/devices/{dev.id}/")
    assert resp.status_code == 204  # 撤销不报 500
    assert not TrustedDevice.objects.filter(id=dev.id).exists()
    # 会话被注销（设备立即下线）
    assert not Session.objects.filter(jti=tokens["jti"]).exists()


@pytest.mark.django_db
def test_trusted_device_refresh_allowed():
    user = PassportUser.objects.create(email="trusted@x.com")
    tokens = issue_tokens(user)
    _make_device(user, trusted=True)

    client = APIClient()
    client.defaults["HTTP_USER_AGENT"] = DEVICE_UA
    resp = client.post(
        "/api/v1/token/refresh/", {"refresh": tokens["refresh"]}, format="json"
    )
    assert resp.status_code == 200
    assert "access" in resp.json()


@pytest.mark.django_db
def test_untrusted_device_refresh_rejected():
    user = PassportUser.objects.create(email="untrusted@x.com")
    tokens = issue_tokens(user)
    _make_device(user, trusted=False)  # 用户已取消该设备信任

    client = APIClient()
    client.defaults["HTTP_USER_AGENT"] = DEVICE_UA
    resp = client.post(
        "/api/v1/token/refresh/", {"refresh": tokens["refresh"]}, format="json"
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == 401


@pytest.mark.django_db
def test_untrust_revokes_device_sessions():
    user = PassportUser.objects.create(email="untrust@x.com")
    client, tokens = _auth_client(user)
    dev = _make_device(user, trusted=True)
    Session.objects.create(
        user=user,
        jti=tokens["jti"],
        device_type=dev.device_type,
        os=dev.os,
        browser=dev.browser,
    )

    resp = client.patch(
        f"/api/v1/devices/{dev.id}/", {"trusted": False}, format="json"
    )
    assert resp.status_code == 200
    dev.refresh_from_db()
    assert dev.trusted is False
    # 取消信任后该设备会话被注销，下次访问需重新验证
    assert not Session.objects.filter(jti=tokens["jti"]).exists()


@pytest.mark.django_db
def test_revoke_succeeds_even_if_blacklist_fails(monkeypatch):
    """Regression: a slow/failing Redis blacklist must NOT block logout.

    The session-row deletion is authoritative; the jti blacklist is best-
    effort. If RevocationStore.revoke raises, the device must still be
    revoked (204) and its session dropped — otherwise the request hangs until
    gunicorn kills the worker (HTTP 500, no traceback). See §9.3 fix.
    """
    import passport.views as views

    def _boom(self, jti, ttl):  # simulate Redis timeout / connection error
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(views.RevocationStore, "revoke", _boom)

    user = PassportUser.objects.create(email="blacklist-fail@x.com")
    client, tokens = _auth_client(user)
    dev = _make_device(user, trusted=True)
    Session.objects.create(
        user=user,
        jti=tokens["jti"],
        device_type=dev.device_type,
        os=dev.os,
        browser=dev.browser,
    )

    resp = client.delete(f"/api/v1/devices/{dev.id}/")
    assert resp.status_code == 204  # 黑名单失败不阻塞、不 500
    assert not TrustedDevice.objects.filter(id=dev.id).exists()
    assert not Session.objects.filter(jti=tokens["jti"]).exists()


# --------------------------------------------------------------------------- #
# Access-token trust gate (§9.3 regression fix):
# Before this gate, an untrusted/revoked device's 30-min access token kept
# auto-logging-in because /api/v1/userinfo/ only verified the JWT signature.
# Now every business view's IsAuthenticatedAndTrusted short-circuits to 401.
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_userinfo_rejects_untrusted_device():
    user = PassportUser.objects.create(email="userinfo-untrusted@x.com")
    # conftest's auto-trust signal has already created a trusted=True row for
    # this user; remove it so the only TrustedDevice in play is the untrusted
    # one we're testing against.
    TrustedDevice.objects.filter(user=user, trusted=True).delete()
    _make_device(user, trusted=False)  # device is known but untrusted
    tokens = issue_tokens(user)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    client.defaults["HTTP_USER_AGENT"] = DEVICE_UA
    resp = client.get("/api/v1/userinfo/")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == 401


@pytest.mark.django_db
def test_userinfo_rejects_revoked_device():
    """No TrustedDevice row at all — as if DELETE /devices/<pk>/ ran earlier."""
    user = PassportUser.objects.create(email="userinfo-revoked@x.com")
    # Strip conftest's auto-trusted device so the gate sees zero rows.
    TrustedDevice.objects.filter(user=user).delete()
    tokens = issue_tokens(user)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    client.defaults["HTTP_USER_AGENT"] = DEVICE_UA
    resp = client.get("/api/v1/userinfo/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_userinfo_allows_trusted_device():
    user = PassportUser.objects.create(email="userinfo-trusted@x.com")
    _make_device(user, trusted=True)
    tokens = issue_tokens(user)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    client.defaults["HTTP_USER_AGENT"] = DEVICE_UA
    resp = client.get("/api/v1/userinfo/")
    assert resp.status_code == 200
    assert resp.json()["email"] == "userinfo-trusted@x.com"


@pytest.mark.django_db
def test_logout_does_not_require_trust():
    """LogoutView must stay reachable even when the device is untrusted,
    so a user can still clear their local tokens after a revoke (§9.3).
    """
    user = PassportUser.objects.create(email="logout-while-untrusted@x.com")
    _make_device(user, trusted=False)
    tokens = issue_tokens(user)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    client.defaults["HTTP_USER_AGENT"] = DEVICE_UA
    resp = client.post("/api/v1/logout/", {}, format="json")
    assert resp.status_code == 200
