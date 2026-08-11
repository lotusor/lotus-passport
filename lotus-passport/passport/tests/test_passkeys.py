"""Tests for Passkey / WebAuthn (§9.4b).

py_webauthn's crypto is mocked so the ceremony can be exercised without a real
authenticator. The challenge store runs on fakeredis (settings.TESTING=True).
"""
import json
import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from passport.models import Passkey, PassportUser
from passport.webauthn import bytes_to_base64url


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _make_user(email="pk@x.com"):
    return PassportUser.objects.create_user(email=email)


# -- fixtures that mock py_webauthn ---------------------------------------- #
@pytest.fixture
def reg_patch():
    fake = type(
        "VerifiedRegistration",
        (),
        {
            "credential_id": b"fake-cred-id-bytes",
            "credential_public_key": b"fake-pubkey-bytes",
            "sign_count": 0,
            "credential_device_type": "platform",
            "credential_backed_up": True,
            "aaguid": uuid.UUID(int=0),
        },
    )()
    with patch("webauthn.generate_registration_options") as g, patch(
        "webauthn.verify_registration_response", return_value=fake
    ) as v, patch(
        "webauthn.options_to_json",
        return_value=json.dumps(
            {
                "challenge": "ch",
                "rp": {"id": "localhost", "name": "莲花通行证"},
                "user": {"id": "u"},
                "pubKeyCredParams": [],
            }
        ),
    ):
        yield {"gen": g, "ver": v}


@pytest.fixture
def auth_patch():
    fake = type(
        "VerifiedAuthentication",
        (),
        {
            "credential_id": b"fake-cred-id-bytes",
            "new_sign_count": 1,
            "credential_device_type": "platform",
            "credential_backed_up": True,
        },
    )()
    with patch("webauthn.generate_authentication_options") as g, patch(
        "webauthn.verify_authentication_response", return_value=fake
    ) as v, patch(
        "webauthn.options_to_json",
        return_value=json.dumps(
            {"challenge": "ch", "rpId": "localhost", "allowCredentials": []}
        ),
    ):
        yield {"gen": g, "ver": v}


# -- list ---------------------------------------------------------------- #
@pytest.mark.django_db
def test_passkey_list_empty(reg_patch):
    user = _make_user()
    resp = _client_for(user).get("/api/v1/security/passkeys/")
    assert resp.status_code == 200
    assert resp.json()["passkeys"] == []


@pytest.mark.django_db
def test_passkey_list_returns_rows(reg_patch):
    user = _make_user()
    Passkey.objects.create(
        user=user, credential_id="cid1", public_key="ab", name="MBP", device_label="本机"
    )
    resp = _client_for(user).get("/api/v1/security/passkeys/")
    assert resp.status_code == 200
    rows = resp.json()["passkeys"]
    assert len(rows) == 1
    assert rows[0]["name"] == "MBP"
    assert "added_at" in rows[0] and "last_used_at" in rows[0]


# -- registration (intentionally disabled: 501 当前功能待开发) ------------- #
@pytest.mark.django_db
def test_register_options_returns_501(reg_patch):
    user = _make_user()
    resp = _client_for(user).post("/api/v1/webauthn/options/register/")
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == 501


@pytest.mark.django_db
def test_register_returns_501(reg_patch):
    user = _make_user()
    client = _client_for(user)
    client.post("/api/v1/webauthn/options/register/")  # prime challenge (no-op now)
    resp = client.post(
        "/api/v1/webauthn/register/",
        {"name": "My Phone", "response": {"id": "x", "response": {"transports": ["internal"]}}},
        format="json",
    )
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == 501


@pytest.mark.django_db
def test_register_rejects_with_501(reg_patch):
    user = _make_user()
    resp = _client_for(user).post(
        "/api/v1/webauthn/register/", {"name": "x"}, format="json"
    )
    assert resp.status_code == 501


@pytest.mark.django_db
def test_register_without_primed_challenge_returns_501(reg_patch):
    user = _make_user()
    resp = _client_for(user).post(
        "/api/v1/webauthn/register/",
        {"response": {"id": "x", "response": {}}},
        format="json",
    )
    assert resp.status_code == 501


# -- delete (owner only) ------------------------------------------------- #
@pytest.mark.django_db
def test_delete_passkey_owner_only(reg_patch):
    u1 = _make_user("a@x.com")
    u2 = _make_user("b@x.com")
    pk = Passkey.objects.create(user=u1, credential_id="cid-del", public_key="ab")
    c1, c2 = _client_for(u1), _client_for(u2)
    assert c2.delete(f"/api/v1/webauthn/{pk.id}/").status_code == 404
    assert c1.delete(f"/api/v1/webauthn/{pk.id}/").status_code == 204
    assert Passkey.objects.filter(id=pk.id).count() == 0


# -- passwordless login -------------------------------------------------- #
@pytest.mark.django_db
def test_auth_options_returns_state(auth_patch):
    client = APIClient()  # public endpoint
    resp = client.post("/api/v1/webauthn/options/auth/")
    assert resp.status_code == 200
    body = resp.json()
    assert "options" in body and "state" in body


@pytest.mark.django_db
def test_verify_issues_tokens_and_updates_sign_count(auth_patch):
    user = _make_user()
    cid = bytes_to_base64url(b"fake-cred-id-bytes")
    Passkey.objects.create(user=user, credential_id=cid, public_key="ab", sign_count=0)
    client = APIClient()
    state = client.post("/api/v1/webauthn/options/auth/").json()["state"]
    resp = client.post(
        "/api/v1/webauthn/verify/",
        {"state": state, "response": {"id": cid, "response": {}}},
        format="json",
    )
    assert resp.status_code == 200, resp.json()
    assert "access" in resp.json()
    pk = Passkey.objects.get(user=user)
    assert pk.sign_count == 1
    assert pk.last_used_at is not None


@pytest.mark.django_db
def test_verify_unknown_credential_401(auth_patch):
    client = APIClient()
    state = client.post("/api/v1/webauthn/options/auth/").json()["state"]
    cid = bytes_to_base64url(b"does-not-exist")
    resp = client.post(
        "/api/v1/webauthn/verify/",
        {"state": state, "response": {"id": cid, "response": {}}},
        format="json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_verify_bad_state_400(auth_patch):
    client = APIClient()
    cid = bytes_to_base64url(b"fake-cred-id-bytes")
    Passkey.objects.create(user=_make_user(), credential_id=cid, public_key="ab")
    resp = client.post(
        "/api/v1/webauthn/verify/",
        {"state": "bogus", "response": {"id": cid, "response": {}}},
        format="json",
    )
    assert resp.status_code == 400


