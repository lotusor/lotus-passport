"""Tests for email-based password reset (§9.4a reset)."""
import pytest
from django.core import mail
from rest_framework.test import APIClient

from passport.models import PassportUser, Session
from passport.ratelimit import PasswordResetStore


def _password_user(email):
    u = PassportUser.objects.create(email=email, username="u_" + email.split("@")[0])
    u.set_password("OldPass123456")
    u.save()
    return u


@pytest.fixture
def smtp_enabled(settings):
    settings.PASSWORD_RESET_ENABLED = True
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    return settings


# --- request ---------------------------------------------------------------- #
@pytest.mark.django_db
def test_reset_request_sends_email(smtp_enabled):
    _password_user("reset1@example.com")
    resp = APIClient().post(
        "/api/v1/security/password/reset-request/",
        {"identifier": "reset1@example.com"},
        format="json",
    )
    assert resp.status_code == 200
    assert len(mail.outbox) == 1
    body = mail.outbox[0].body
    assert "token=" in body
    assert "reset1@example.com" in mail.outbox[0].to


@pytest.mark.django_db
def test_reset_request_by_username(smtp_enabled):
    _password_user("reset2@example.com")  # username = u_reset2
    resp = APIClient().post(
        "/api/v1/security/password/reset-request/",
        {"identifier": "u_reset2"},
        format="json",
    )
    assert resp.status_code == 200
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_reset_request_no_accountEnumeration(smtp_enabled):
    """Unknown identifier returns the same 200 — no account enumeration."""
    resp = APIClient().post(
        "/api/v1/security/password/reset-request/",
        {"identifier": "nobody@example.com"},
        format="json",
    )
    assert resp.status_code == 200
    assert len(mail.outbox) == 0
    assert resp.json()["detail"]


@pytest.mark.django_db
def test_reset_request_503_when_smtp_unconfigured(settings):
    settings.PASSWORD_RESET_ENABLED = False
    resp = APIClient().post(
        "/api/v1/security/password/reset-request/",
        {"identifier": "x@example.com"},
        format="json",
    )
    assert resp.status_code == 503


# --- confirm ---------------------------------------------------------------- #
@pytest.mark.django_db
def test_reset_confirm_sets_password_and_revokes_sessions(smtp_enabled):
    user = _password_user("reset3@example.com")
    Session.objects.create(user=user, jti="jti-reset-1", device="Chrome")
    token = PasswordResetStore().save(user.pk)

    resp = APIClient().post(
        "/api/v1/security/password/reset/",
        {"token": token, "new_password": "NewPass123456"},
        format="json",
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.check_password("NewPass123456")
    assert user.password_changed_at is not None
    # every session row is gone (old password treated as compromised)
    assert not Session.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_reset_confirm_token_single_use(smtp_enabled):
    user = _password_user("reset4@example.com")
    token = PasswordResetStore().save(user.pk)
    c = APIClient()
    r1 = c.post(
        "/api/v1/security/password/reset/",
        {"token": token, "new_password": "NewPass123456"},
        format="json",
    )
    assert r1.status_code == 200
    r2 = c.post(
        "/api/v1/security/password/reset/",
        {"token": token, "new_password": "Another123456"},
        format="json",
    )
    assert r2.status_code == 400


@pytest.mark.django_db
def test_reset_confirm_rejects_weak_password(smtp_enabled):
    user = _password_user("reset5@example.com")
    token = PasswordResetStore().save(user.pk)
    resp = APIClient().post(
        "/api/v1/security/password/reset/",
        {"token": token, "new_password": "short"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_reset_confirm_rejects_garbage_token(smtp_enabled):
    resp = APIClient().post(
        "/api/v1/security/password/reset/",
        {"token": "no-such-token", "new_password": "NewPass123456"},
        format="json",
    )
    assert resp.status_code == 400
