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
