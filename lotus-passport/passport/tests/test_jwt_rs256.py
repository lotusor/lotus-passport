"""RS256 signing + JWKS verification (no external calls).

Proves the unified-auth value proposition: a downstream integrator can verify a
passport JWT using ONLY the public key published at ``/.well-known/jwks.json`` —
never the signing secret.
"""
import jwt
import pytest
import uuid
from django.conf import settings

from passport.jwt import issue_tokens
from passport.models import PassportUser

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return PassportUser.objects.create(
        passport_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        nickname="rsa-tester",
        email="rsa@lotus.local",
    )


def test_algorithm_is_rs256():
    assert settings.SIMPLE_JWT["ALGORITHM"] == "RS256"


def test_token_header_carries_kid(user):
    tokens = issue_tokens(user)
    header = jwt.get_unverified_header(tokens["access"])
    assert header.get("alg") == "RS256"
    assert header.get("kid") == settings.JWT_KID


def test_jwks_publishes_public_key(client):
    resp = client.get("/api/v1/.well-known/jwks.json")
    assert resp.status_code == 200
    body = resp.json()
    assert "keys" in body
    assert len(body["keys"]) == 1
    jwk = body["keys"][0]
    assert jwk["kty"] == "RSA"
    assert jwk["alg"] == "RS256"
    assert jwk["kid"] == settings.JWT_KID
    # modulus must be a sizable base64url string
    assert len(jwk["n"]) > 100


def test_verify_access_token_with_jwks_public_key(user):
    tokens = issue_tokens(user)
    public_key_pem = settings.SIMPLE_JWT["VERIFYING_KEY"]
    # Integrator side: decode using the PUBLIC key only.
    decoded = jwt.decode(
        tokens["access"],
        public_key_pem,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
    assert decoded["passport_user_id"] == user.passport_user_id
    assert decoded["user_id"] == str(user.id)


def test_userinfo_accepts_rs256_token(user, client):
    tokens = issue_tokens(user)
    resp = client.get(
        "/api/v1/userinfo/",
        HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
    )
    assert resp.status_code == 200
    assert resp.json()["passport_user_id"] == str(user.passport_user_id)
