"""Tests for email verification codes (登录即注册 / 绑定 / 换绑双重验证)."""
import pytest
from django.core import mail
from rest_framework.test import APIClient

from passport.models import PassportUser, TrustedDevice
from passport.ratelimit import EmailCodeStore


@pytest.fixture
def smtp_enabled(settings):
    settings.PASSWORD_RESET_ENABLED = True
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    return settings


def _password_user(email):
    u = PassportUser.objects.create(email=email, username="u_" + email.split("@")[0])
    u.set_password("OldPass123456")
    u.save()
    return u


def _auth_client(user):
    from passport.jwt import issue_tokens

    tokens = issue_tokens(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


def _trust_device(user, ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"):
    """登录视图会自动落 TrustedDevice；测试直连 API 时手动建信任行。"""
    return TrustedDevice.objects.create(
        user=user, device_type="desktop", os="Windows", browser="Chrome", trusted=True
    )


def _last_code(email, purpose) -> str:
    """从 locmem outbox 提取刚发出的验证码（由 store 直接写入更可靠）。"""
    store = EmailCodeStore()
    # 从 redis key 反查不可行（码只存值）；改用测试钩子：发送前 monkeypatch 太重，
    # 直接用 outbox 正文里的 6 位数。
    for m in reversed(mail.outbox):
        if email.lower() in [r.lower() for r in m.to]:
            import re as _re
            found = _re.search(r"\b(\d{6})\b", m.body)
            if found:
                return found.group(1)
    raise AssertionError(f"outbox 中无发给 {email} 的验证码邮件")


# --- 登录即注册 -------------------------------------------------------------- #
@pytest.mark.django_db
def test_email_login_existing_user(smtp_enabled):
    _password_user("exist@example.com")
    c = APIClient()
    assert c.post(
        "/api/v1/security/email/send-code/",
        {"email": "exist@example.com", "purpose": "login"},
        format="json",
    ).status_code == 200
    code = _last_code("exist@example.com", "login")
    resp = c.post(
        "/api/v1/login/email/",
        {"email": "exist@example.com", "code": code},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["access"]
    assert resp.json()["created"] is False


@pytest.mark.django_db
def test_email_login_registers_new_user(smtp_enabled):
    c = APIClient()
    assert c.post(
        "/api/v1/security/email/send-code/",
        {"email": "brand.new@example.com", "purpose": "login"},
        format="json",
    ).status_code == 200
    code = _last_code("brand.new@example.com", "login")
    resp = c.post(
        "/api/v1/login/email/",
        {"email": "brand.new@example.com", "code": code},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    u = PassportUser.objects.get(email="brand.new@example.com")
    assert not u.has_usable_password()  # 自动注册无密码


@pytest.mark.django_db
def test_email_login_wrong_code(smtp_enabled):
    _password_user("wrong@example.com")
    c = APIClient()
    c.post(
        "/api/v1/security/email/send-code/",
        {"email": "wrong@example.com", "purpose": "login"},
        format="json",
    )
    resp = c.post(
        "/api/v1/login/email/",
        {"email": "wrong@example.com", "code": "000000"},
        format="json",
    )
    assert resp.status_code == 401


# --- 首次绑定 ---------------------------------------------------------------- #
@pytest.mark.django_db
def test_bind_email_success(smtp_enabled):
    # OAuth-only 用户无邮箱（模拟 QQ/微信登录建号）
    user = PassportUser.objects.create_user(email=None)
    _trust_device(user)
    c = _auth_client(user)
    assert c.post(
        "/api/v1/security/email/send-code/",
        {"email": "bound@example.com", "purpose": "bind"},
        format="json",
    ).status_code == 200
    code = _last_code("bound@example.com", "bind")
    resp = c.post(
        "/api/v1/security/email/bind/",
        {"email": "bound@example.com", "code": code},
        format="json",
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.email == "bound@example.com"


@pytest.mark.django_db
def test_bind_requires_code_to_target_email(smtp_enabled):
    """绑定的码必须验证目标邮箱（防绑他人邮箱）。"""
    user = PassportUser.objects.create_user(email=None)
    _trust_device(user)
    c = _auth_client(user)
    c.post(
        "/api/v1/security/email/send-code/",
        {"email": "target@example.com", "purpose": "bind"},
        format="json",
    )
    # 用错误码
    resp = c.post(
        "/api/v1/security/email/bind/",
        {"email": "target@example.com", "code": "111111"},
        format="json",
    )
    assert resp.status_code == 401
    user.refresh_from_db()
    assert not user.email


@pytest.mark.django_db
def test_bind_rejects_taken_email(smtp_enabled):
    _password_user("taken@example.com")
    user = PassportUser.objects.create_user(email=None)
    _trust_device(user)
    c = _auth_client(user)
    resp = c.post(
        "/api/v1/security/email/send-code/",
        {"email": "taken@example.com", "purpose": "bind"},
        format="json",
    )
    assert resp.status_code == 409


# --- 换绑（双重验证）---------------------------------------------------------- #
@pytest.mark.django_db
def test_change_email_requires_both_codes(smtp_enabled):
    user = _password_user("old@example.com")
    _trust_device(user)
    c = _auth_client(user)
    # 两个码分别发到新邮箱和旧邮箱
    assert c.post(
        "/api/v1/security/email/send-code/",
        {"email": "new@example.com", "purpose": "new"},
        format="json",
    ).status_code == 200
    assert c.post(
        "/api/v1/security/email/send-code/",
        {"email": "old@example.com", "purpose": "old"},
        format="json",
    ).status_code == 200
    new_code = _last_code("new@example.com", "new")
    old_code = _last_code("old@example.com", "old")

    # 只带 new_code（old_code 填错码）→ 401，且 new_code 已消耗（单次性）
    resp = c.post(
        "/api/v1/security/email/change/",
        {"new_email": "new@example.com", "new_code": new_code, "old_code": "999999",
         "current_password": "OldPass123456"},
        format="json",
    )
    assert resp.status_code == 401
    user.refresh_from_db()
    assert user.email == "old@example.com"  # 未换绑

    # 重新取新码（60s 频率限制针对发送；store 直接写入绕过）
    new_code2 = EmailCodeStore().save("new@example.com", "new")
    # 两码齐全 + 密码 → 200
    resp = c.post(
        "/api/v1/security/email/change/",
        {"new_email": "new@example.com", "new_code": new_code2, "old_code": old_code,
         "current_password": "OldPass123456"},
        format="json",
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.email == "new@example.com"


@pytest.mark.django_db
def test_change_email_requires_password_stepup(smtp_enabled):
    user = _password_user("pw@example.com")
    _trust_device(user)
    c = _auth_client(user)
    c.post("/api/v1/security/email/send-code/",
           {"email": "nx@example.com", "purpose": "new"}, format="json")
    c.post("/api/v1/security/email/send-code/",
           {"email": "pw@example.com", "purpose": "old"}, format="json")
    new_code = _last_code("nx@example.com", "new")
    old_code = _last_code("pw@example.com", "old")
    # 有密码账户但密码错 → 400
    resp = c.post(
        "/api/v1/security/email/change/",
        {"new_email": "nx@example.com", "new_code": new_code, "old_code": old_code,
         "current_password": "WRONG"},
        format="json",
    )
    assert resp.status_code == 400
    user.refresh_from_db()
    assert user.email == "pw@example.com"


@pytest.mark.django_db
def test_change_email_new_must_differ(smtp_enabled):
    user = _password_user("same@example.com")
    _trust_device(user)
    c = _auth_client(user)
    resp = c.post(
        "/api/v1/security/email/send-code/",
        {"email": "same@example.com", "purpose": "new"},
        format="json",
    )
    assert resp.status_code == 400


# --- code store 行为 ---------------------------------------------------------- #
@pytest.mark.django_db
def test_email_code_burns_after_5_wrong_attempts(smtp_enabled):
    store = EmailCodeStore()
    code = store.save("brute@example.com", "login")
    for i in range(5):
        assert store.verify("brute@example.com", "login", "000000") is False
    # 第 5 次错误后码作废：正确码也验不过
    assert store.verify("brute@example.com", "login", code) is False


@pytest.mark.django_db
def test_email_code_single_use(smtp_enabled):
    store = EmailCodeStore()
    code = store.save("once@example.com", "login")
    assert store.verify("once@example.com", "login", code) is True
    assert store.verify("once@example.com", "login", code) is False


@pytest.mark.django_db
def test_send_code_unauthenticated_bind_rejected(smtp_enabled):
    c = APIClient()
    resp = c.post(
        "/api/v1/security/email/send-code/",
        {"email": "x@example.com", "purpose": "bind"},
        format="json",
    )
    assert resp.status_code == 401
