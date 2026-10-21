"""Generic (provider-agnostic) OAuth login entry tests.

GET /api/v1/oauth/login/  -> mint one-time ticket + passport-web login URL
POST /api/v1/oauth/continue/ -> ticket + web JWT => single-use code for app
"""
import pytest
from rest_framework.test import APIClient

from passport.jwt import issue_tokens
from passport.models import PassportUser
from passport.ratelimit import (
    AuthCodeStore,
    GenericLoginTicketStore,
    pkce_s256_challenge,
)

REDIRECT = "http://localhost:5180/auth/callback"  # TESTING 放行 localhost
VERIFIER = "test-verifier-test-verifier-test-verifier-123456"


def _make_user(username="generic-user"):
    return PassportUser.objects.create(
        email=f"{username}@example.com", username=username, nickname=username
    )


# --- GET /login/ ------------------------------------------------------------ #
@pytest.mark.django_db
def test_generic_login_rejects_disallowed_redirect():
    client = APIClient()
    r = client.get(
        "/api/v1/oauth/login/", {"redirect_uri": "https://evil.example.com/cb"}
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_generic_login_mints_ticket_and_login_url():
    client = APIClient()
    r = client.get(
        "/api/v1/oauth/login/",
        {
            "redirect_uri": REDIRECT,
            "code_challenge": pkce_s256_challenge(VERIFIER),
            "code_challenge_method": "S256",
        },
    )
    assert r.status_code == 200
    login_url = r.data["login_url"]
    assert "/login?oticket=" in login_url
    ticket = login_url.split("oticket=")[1]
    payload = GenericLoginTicketStore().consume(ticket)
    assert payload is not None
    assert payload["redirect_uri"] == REDIRECT
    assert payload["code_challenge"] == pkce_s256_challenge(VERIFIER)


# --- POST /continue/ -------------------------------------------------------- #
@pytest.mark.django_db
def test_continue_requires_authentication():
    client = APIClient()
    r = client.post("/api/v1/oauth/continue/", {"ticket": "whatever"}, format="json")
    assert r.status_code == 401


@pytest.mark.django_db
def test_continue_rejects_invalid_ticket():
    user = _make_user("gen-invalid")
    client = APIClient()
    tokens = issue_tokens(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    r = client.post("/api/v1/oauth/continue/", {"ticket": "bogus"}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_continue_mints_single_use_code_pkce_bound():
    user = _make_user("gen-ok")
    challenge = pkce_s256_challenge(VERIFIER)
    ticket = GenericLoginTicketStore().save(
        redirect_uri=REDIRECT,
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    client = APIClient()
    tokens = issue_tokens(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    r = client.post("/api/v1/oauth/continue/", {"ticket": ticket}, format="json")
    assert r.status_code == 200
    redirect_url = r.data["redirect_url"]
    assert redirect_url.startswith(REDIRECT)
    assert "code=" in redirect_url
    code = redirect_url.split("code=")[1]
    stored = AuthCodeStore().consume(code)
    assert stored is not None
    assert stored["code_challenge"] == challenge
    assert stored["passport_user_id"] == tokens["passport_user_id"]
    # 票据单次：第二次 continue 应 400
    r2 = client.post("/api/v1/oauth/continue/", {"ticket": ticket}, format="json")
    assert r2.status_code == 400


@pytest.mark.django_db
def test_continue_rejects_forged_ticket_with_bad_redirect(monkeypatch):
    """redis 里被伪造了白名单外 redirect_uri 的票据 → continue 拒绝。"""
    user = _make_user("gen-forge")
    ticket = GenericLoginTicketStore().save(
        redirect_uri="https://evil.example.com/cb",
        code_challenge=None,
        code_challenge_method=None,
    )
    client = APIClient()
    tokens = issue_tokens(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    r = client.post("/api/v1/oauth/continue/", {"ticket": ticket}, format="json")
    assert r.status_code == 400
