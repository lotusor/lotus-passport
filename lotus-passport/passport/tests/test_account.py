"""Tests for account-management endpoints (§9.1 / §9.3 / §9.4d / §9.4e)."""
import pytest
from rest_framework.test import APIClient

from passport.jwt import issue_tokens
from passport.models import LoginEvent, PassportUser, Session, TrustedDevice
from passport.auth_events import record_login_success


def _auth_client(user: PassportUser) -> tuple[APIClient, dict]:
    tokens = issue_tokens(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client, tokens


@pytest.mark.django_db
def test_profile_get_includes_identity_fields():
    # 用 create_user（与 OAuth-only 注册路径一致）确保是真正的无密码账户：
    # 直接 objects.create 会把 password 留空字符串，而 Django 的
    # has_usable_password() 对非空串（即便为空）会误判为 True。
    user = PassportUser.objects.create_user(
        email="u@x.com", nickname="小越", username="yue", bio="算法爱好者"
    )
    user.set_phone("13800006620")
    user.save()
    client, _ = _auth_client(user)

    resp = client.get("/api/v1/profile/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "yue"
    assert body["bio"] == "算法爱好者"
    assert body["phone"] == "13800006620"
    assert body["email"] == "u@x.com"
    # §9.4f：前端靠该字段判断是否渲染注销密码输入框（无密码账户 has_usable_password()=False）
    assert body["has_password"] is False


@pytest.mark.django_db
def test_profile_patch_updates_fields_and_encrypts_phone():
    user = PassportUser.objects.create(email="p@x.com", nickname="旧名")
    client, _ = _auth_client(user)

    resp = client.patch(
        "/api/v1/profile/",
        {"nickname": "新名", "username": "newname", "phone": "13900001111", "bio": "hi"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["nickname"] == "新名"
    assert body["username"] == "newname"
    assert body["phone"] == "13900001111"
    assert body["bio"] == "hi"

    user.refresh_from_db()
    assert user.phone == "13900001111"  # 解密后一致
    assert user.phone_enc and "13900001111" not in user.phone_enc  # 明文未落库


@pytest.mark.django_db
def test_profile_patch_duplicate_username_conflicts():
    a = PassportUser.objects.create(email="a@x.com", username="taken")
    b = PassportUser.objects.create(email="b@x.com")
    client, _ = _auth_client(b)

    resp = client.patch("/api/v1/profile/", {"username": "taken"}, format="json")
    # DRF 的 ModelSerializer 对 unique 字段自动加 UniqueValidator，重复即 400
    # （并发竞态才落到视图里的 IntegrityError → 409 兜底）。
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == 400
    assert "username" in resp.json()["error"]["message"].lower()
    b.refresh_from_db()
    assert b.username is None


@pytest.mark.django_db
def test_profile_requires_auth():
    client = APIClient()
    resp = client.get("/api/v1/profile/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_sessions_list_marks_current_and_revoke():
    user = PassportUser.objects.create(email="s@x.com")
    client, tokens = _auth_client(user)
    # 模拟一次登录，写入当前会话（jti 来自 token）
    record_login_success(user, jti=tokens["jti"])
    # 再写一个"其它"会话
    Session.objects.create(user=user, jti="other-jti", device="Chrome · macOS", ip="1.2.3.4")

    resp = client.get("/api/v1/sessions/")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    current = [r for r in rows if r["current"]]
    assert len(current) == 1
    assert current[0]["jti"] == tokens["jti"]

    # 注销其它会话
    resp = client.delete("/api/v1/sessions/")
    assert resp.status_code == 200
    assert resp.json()["revoked"] == 1
    assert Session.objects.filter(user=user).count() == 1

    # 不能注销当前会话
    other = Session.objects.create(user=user, jti="x-jti", device="X")
    resp = client.delete(f"/api/v1/sessions/{other.id}/")
    assert resp.status_code == 204
    # 当前会话仍在
    assert Session.objects.filter(jti=tokens["jti"]).exists()


@pytest.mark.django_db
def test_devices_crud():
    user = PassportUser.objects.create(email="d@x.com")
    client, _ = _auth_client(user)

    assert client.get("/api/v1/devices/").json() == []

    dev = TrustedDevice.objects.create(user=user, name="MacBook", trusted=False)
    resp = client.patch(
        f"/api/v1/devices/{dev.id}/", {"trusted": True, "name": "我的 MacBook"}, format="json"
    )
    assert resp.status_code == 200
    dev.refresh_from_db()
    assert dev.trusted is True
    assert dev.name == "我的 MacBook"
    assert dev.first_trusted_at is not None

    # 不能删别人的设备
    other = PassportUser.objects.create(email="o@x.com")
    other_dev = TrustedDevice.objects.create(user=other, name=" stranger")
    resp = client.delete(f"/api/v1/devices/{other_dev.id}/")
    assert resp.status_code == 404

    resp = client.delete(f"/api/v1/devices/{dev.id}/")
    assert resp.status_code == 204
    assert not TrustedDevice.objects.filter(id=dev.id).exists()


@pytest.mark.django_db
def test_login_history_recorded():
    user = PassportUser.objects.create(email="l@x.com")
    client, tokens = _auth_client(user)
    record_login_success(user, jti=tokens["jti"])
    LoginEvent.objects.create(user=user, status="failed", reason="bad_pwd", ip="9.9.9.9")

    resp = client.get("/api/v1/security/login-history/")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert any(r["status"] == "failed" for r in rows)
