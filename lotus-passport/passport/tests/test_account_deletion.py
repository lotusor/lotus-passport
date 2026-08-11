"""Tests for account self-deletion (§9.4f)."""
import pytest
from rest_framework.test import APIClient

from passport.jwt import issue_tokens
from passport.models import (
    AccountDeletion,
    LoginEvent,
    OAuthAccount,
    Passkey,
    PassportUser,
    Session,
    TrustedDevice,
)
from passport.revocation import RevocationStore


def _auth_client(user):
    tokens = issue_tokens(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client, tokens


def _password_user(email, password):
    u = PassportUser.objects.create(email=email)
    u.set_password(password)
    u.save()
    return u


def _oauth_only_user(email):
    u = PassportUser.objects.create(email=email)
    u.set_unusable_password()
    u.save()
    return u


def _seed_related(user):
    OAuthAccount.objects.create(user=user, provider="github", provider_user_id="gh-1")
    Passkey.objects.create(user=user, credential_id="cred-1", public_key="deadbeef")
    Session.objects.create(user=user, jti="jti-session-1", device="Chrome")
    TrustedDevice.objects.create(user=user, name="laptop")
    LoginEvent.objects.create(user=user, status="success", ip="1.2.3.4")


# --- gates ----------------------------------------------------------------- #
@pytest.mark.django_db
def test_delete_requires_auth():
    resp = APIClient().delete("/api/v1/profile/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_delete_requires_confirm():
    user = _password_user("c1@x.com", "pw123456")
    client, _ = _auth_client(user)
    resp = client.delete("/api/v1/profile/")
    assert resp.status_code == 400
    assert PassportUser.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_delete_requires_current_password_when_set():
    user = _password_user("c2@x.com", "pw123456")
    client, _ = _auth_client(user)
    resp = client.delete(
        "/api/v1/profile/",
        {"confirm": True, "current_password": "wrong"},
        format="json",
    )
    assert resp.status_code == 400
    assert PassportUser.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_oauth_only_delete_with_confirm_only():
    user = _oauth_only_user("c3@x.com")
    client, _ = _auth_client(user)
    resp = client.delete("/api/v1/profile/", {"confirm": True}, format="json")
    assert resp.status_code == 204
    assert not PassportUser.objects.filter(pk=user.pk).exists()


# --- cascade + audit ------------------------------------------------------- #
@pytest.mark.django_db
def test_delete_cascades_related_and_audits():
    user = _password_user("c4@x.com", "pw123456")
    _seed_related(user)
    pid = str(user.passport_id)
    client, _ = _auth_client(user)
    resp = client.delete(
        "/api/v1/profile/",
        {"confirm": True, "current_password": "pw123456"},
        format="json",
    )
    assert resp.status_code == 204

    assert not PassportUser.objects.filter(pk=user.pk).exists()
    assert not OAuthAccount.objects.filter(user_id=user.pk).exists()
    assert not Passkey.objects.filter(user_id=user.pk).exists()
    assert not Session.objects.filter(user_id=user.pk).exists()
    assert not TrustedDevice.objects.filter(user_id=user.pk).exists()
    assert not LoginEvent.objects.filter(user_id=user.pk).exists()

    # Anonymized audit row exists (only passport_id retained, no PII).
    audit = AccountDeletion.objects.get(passport_id=pid)
    assert audit.passport_id == pid


@pytest.mark.django_db
def test_delete_revokes_session_jti():
    user = _password_user("c5@x.com", "pw123456")
    Session.objects.create(user=user, jti="jti-revoke-me", device="Chrome")
    client, _ = _auth_client(user)
    resp = client.delete(
        "/api/v1/profile/",
        {"confirm": True, "current_password": "pw123456"},
        format="json",
    )
    assert resp.status_code == 204
    assert RevocationStore().is_revoked("jti-revoke-me") is True
