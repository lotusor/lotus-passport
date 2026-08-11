"""Discovery surface consumed by the integrator SDKs.

The SDK bootstraps from a single ``base_url``: it fetches
``/.well-known/passport-configuration`` to learn where JWKS and userinfo live,
then pins ``issuer``. These tests lock that contract down — breaking any of it
silently breaks every downstream app.
"""
import uuid

import jwt
import pytest
from django.conf import settings
from django.test import override_settings

from passport.jwt import issue_tokens
from passport.models import PassportUser

pytestmark = pytest.mark.django_db

# Deterministic OAuth config for the discovery contract: regardless of what the
# local .env ships (e.g. real GitHub creds), the test env must advertise no
# providers so `providers_supported == []` stays meaningful.
_NO_PROVIDERS = {
    name: {"client_id": "", "client_secret": ""}
    for name in ("github", "wechat", "qq")
}


@pytest.fixture
def user():
    return PassportUser.objects.create(
        passport_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        nickname="sdk-tester",
        email="sdk@lotus.local",
    )


def test_jwks_served_at_root_well_known(client):
    """SDKs / generic jose clients look at the ROOT path, not /api/v1/."""
    resp = client.get("/.well-known/jwks.json")
    assert resp.status_code == 200
    assert resp.json()["keys"][0]["kid"] == settings.JWT_KID


def test_root_and_legacy_jwks_are_identical(client):
    root = client.get("/.well-known/jwks.json").json()
    legacy = client.get("/api/v1/.well-known/jwks.json").json()
    assert root == legacy


@override_settings(OAUTH_PROVIDERS=_NO_PROVIDERS)
def test_configuration_document(client):
    resp = client.get("/.well-known/passport-configuration")
    assert resp.status_code == 200
    body = resp.json()

    assert body["issuer"] == settings.JWT_ISSUER
    assert body["jwks_uri"].endswith("/.well-known/jwks.json")
    assert body["userinfo_endpoint"].endswith("/api/v1/userinfo/")
    assert body["token_refresh_endpoint"].endswith("/api/v1/token/refresh/")
    assert "RS256" in body["id_token_signing_alg_values_supported"]
    assert "passport_user_id" in body["claims_supported"]
    # Nothing is configured in the test env, so no provider should be advertised.
    assert body["providers_supported"] == []


def test_tokens_carry_issuer_claim(user):
    tokens = issue_tokens(user)
    decoded = jwt.decode(
        tokens["access"],
        settings.SIMPLE_JWT["VERIFYING_KEY"],
        algorithms=["RS256"],
        issuer=settings.JWT_ISSUER,  # would raise InvalidIssuerError if missing
        options={"verify_aud": False},
    )
    assert decoded["iss"] == settings.JWT_ISSUER


def test_token_with_foreign_issuer_is_rejected(user):
    """An integrator pinning `iss` must reject a token minted elsewhere."""
    tokens = issue_tokens(user)
    with pytest.raises(jwt.InvalidIssuerError):
        jwt.decode(
            tokens["access"],
            settings.SIMPLE_JWT["VERIFYING_KEY"],
            algorithms=["RS256"],
            issuer="some-other-issuer",
            options={"verify_aud": False},
        )
