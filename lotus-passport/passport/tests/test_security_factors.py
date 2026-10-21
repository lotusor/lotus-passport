"""Tests for password (§9.4a) endpoints."""
import uuid

import pytest
from django.conf import settings
from django.test.utils import override_settings
from rest_framework.test import APIClient

from passport.jwt import issue_tokens
from passport.models import PassportUser, Session
from passport.auth_events import record_login_success


def _auth_client(user: PassportUser) -> tuple[APIClient, dict]:
    tokens = issue_tokens(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client, tokens


def _make_password_user(email: str, password: str) -> PassportUser:
    u = PassportUser.objects.create(email=email)
    u.set_password(password)
    u.save()
    return u


def _make_oauth_only_user(email: str) -> PassportUser:
    # Mirror a real OAuth account: no usable password factor.
    u = PassportUser.objects.create(email=email)
    u.set_unusable_password()
    u.save()
    return u


# --------------------------------------------------------------------------- #
# §9.4a 密码
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_password_status_reports_no_password_for_oauth_only():
    user = _make_oauth_only_user("oauth@x.com")
    client, _ = _auth_client(user)
    resp = client.get("/api/v1/security/password/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_password"] is False


@pytest.mark.django_db
def test_oauth_only_user_can_set_password():
    user = _make_oauth_only_user("set@x.com")
    client, _ = _auth_client(user)
    resp = client.post(
        "/api/v1/security/password/change/", {"new_password": "abc12345"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.json()["has_password"] is True

    # The new password now works at the login endpoint.
    login = APIClient().post(
        "/api/v1/login/", {"identifier": "set@x.com", "password": "abc12345"}, format="json"
    )
    assert login.status_code == 200
    assert "access" in login.json()


@pytest.mark.django_db
def test_password_change_requires_current_password():
    user = _make_password_user("chg@x.com", "oldpass123")
    client, _ = _auth_client(user)

    # Missing current password -> rejected.
    r1 = client.post(
        "/api/v1/security/password/change/", {"new_password": "newpass123"}, format="json"
    )
    assert r1.status_code == 400

    # Wrong current password -> rejected.
    r2 = client.post(
        "/api/v1/security/password/change/",
        {"current_password": "wrong", "new_password": "newpass123"},
        format="json",
    )
    assert r2.status_code == 400

    # Correct current password -> accepted.
    r3 = client.post(
        "/api/v1/security/password/change/",
        {"current_password": "oldpass123", "new_password": "newpass123"},
        format="json",
    )
    assert r3.status_code == 200
    assert r3.json()["has_password"] is True


@pytest.mark.django_db
def test_password_change_rejects_weak_password():
    user = _make_password_user("weak@x.com", "oldpass123")
    client, _ = _auth_client(user)
    r = client.post(
        "/api/v1/security/password/change/",
        {"current_password": "oldpass123", "new_password": "short"},
        format="json",
    )
    assert r.status_code == 400
    assert "密码" in r.json()["error"]["message"]


@pytest.mark.django_db
def test_password_change_revokes_other_sessions():
    user = _make_password_user("rev@x.com", "oldpass123")
    client, tokens = _auth_client(user)
    # Current session row (jti == token jti).
    record_login_success(user, jti=tokens["jti"])
    # A different, still-live session for the same user.
    Session.objects.create(user=user, jti="other-jti", device="Chrome", ip="1.2.3.4")

    r = client.post(
        "/api/v1/security/password/change/",
        {"current_password": "oldpass123", "new_password": "brandnew1"},
        format="json",
    )
    assert r.status_code == 200
    # Other session revoked, current session preserved.
    assert not Session.objects.filter(jti="other-jti").exists()
    assert Session.objects.filter(jti=tokens["jti"]).exists()


@pytest.mark.django_db
def test_password_login_success_and_wrong_password():
    user = _make_password_user("login@x.com", "secret123")
    # Success.
    ok = APIClient().post(
        "/api/v1/login/", {"identifier": "login@x.com", "password": "secret123"}, format="json"
    )
    assert ok.status_code == 200
    assert "access" in ok.json()

    # Wrong password -> 401 (uniform, no user enumeration).
    bad = APIClient().post(
        "/api/v1/login/", {"identifier": "login@x.com", "password": "nope"}, format="json"
    )
    assert bad.status_code == 401
    assert "账号或密码不正确" in bad.json()["error"]["message"]


@pytest.mark.django_db
def test_password_login_rejects_oauth_only_account():
    # An account with no usable password must not be distinguishable here.
    user = _make_oauth_only_user("noauth@x.com")
    r = APIClient().post(
        "/api/v1/login/", {"identifier": "noauth@x.com", "password": "whatever"}, format="json"
    )
    assert r.status_code == 401
    assert "账号或密码不正确" in r.json()["error"]["message"]


@override_settings(HCAPTCHA_SECRET_KEY="", CAPTCHA_ENABLED=False)
@pytest.mark.django_db
def test_password_login_locks_after_threshold(client):
    """§一.B — repeated failures lock the account (identity dimension)."""
    user = _make_password_user("lockme@x.com", "secret123")
    # (threshold - 1) wrong attempts -> still 401 (uniform, no enumeration).
    for _ in range(settings.ACCOUNT_LOCKOUT_THRESHOLD - 1):
        r = client.post(
            "/api/v1/login/",
            {"identifier": "lockme@x.com", "password": "wrong"},
            format="json",
        )
        assert r.status_code == 401
    # The threshold-th failure trips the lock itself.
    r = client.post(
        "/api/v1/login/",
        {"identifier": "lockme@x.com", "password": "wrong"},
        format="json",
    )
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "locked"
    assert r.json()["error"]["retry_after"] > 0
    # Even the correct password is blocked while locked.
    r = client.post(
        "/api/v1/login/",
        {"identifier": "lockme@x.com", "password": "secret123"},
        format="json",
    )
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "locked"


@override_settings(MAX_SESSIONS_PER_USER=3)
@pytest.mark.django_db
def test_session_cap_enforced_on_login():
    """§一.F — login never grows a user's sessions beyond the cap."""
    user = _make_password_user("cap@x.com", "secret123")
    for _ in range(5):
        record_login_success(user, jti=str(uuid.uuid4()), request=None)
    assert Session.objects.filter(user=user).count() == 3
