"""CAPTCHA (hCaptcha) gate on the password-login endpoint (docs/captcha-plan.md).

Covers: default-off (no key), captcha_required after the failure threshold,
captcha_invalid rejection without 误锁, and lockout winning over captcha.

Note on the lockout interaction: once the failure threshold (3) is hit the gate
requires a solved captcha before *further* failures are counted, so reaching the
lockout threshold (5) requires solving captcha on attempts 4 and 5. That is the
intended behaviour — a bot that cannot solve the captcha can never be locked out
either, and an already-locked account bypasses the gate entirely.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from passport.models import PassportUser

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/v1/login/"
IDENT = "captester"
PASSWD = "correct-horse-battery-staple"


@pytest.fixture
def user():
    u = PassportUser.objects.create(
        passport_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        nickname="cap",
        email="cap@lotus.local",
        username=IDENT,
    )
    u.set_password(PASSWD)
    u.save()
    return u


def _fail(c, captcha=None):
    body = {"identifier": IDENT, "password": "wrong-password"}
    if captcha:
        body["captcha"] = captcha
    return c.post(LOGIN_URL, body, format="json")


@override_settings(HCAPTCHA_SECRET_KEY="", CAPTCHA_ENABLED=False)
def test_captcha_disabled_by_default(user):
    c = APIClient()
    # Without a secret the gate must never fire; the account still locks at 5.
    for _ in range(4):
        r = _fail(c)
        assert r.status_code == 401
    r = _fail(c)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "locked"


@override_settings(HCAPTCHA_SECRET_KEY="x", CAPTCHA_ENABLED=True)
def test_captcha_required_after_threshold(user):
    c = APIClient()
    for _ in range(3):
        r = _fail(c)
        assert r.status_code == 401
    # 4th attempt with no token -> 400 captcha_required (does NOT consume a failure)
    r = _fail(c)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "captcha_required"
    # 5th attempt with a (mocked) valid token -> proceeds to password check.
    with patch("passport.captcha.requests.post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"success": True})
        r = _fail(c, captcha="tok")
        assert r.status_code == 401  # token valid, but password wrong
        assert r.json()["error"].get("captcha_required") is True  # count now >= threshold


@override_settings(HCAPTCHA_SECRET_KEY="x", CAPTCHA_ENABLED=True)
def test_captcha_invalid_token_rejected(user):
    c = APIClient()
    for _ in range(3):
        _fail(c)
    with patch("passport.captcha.requests.post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"success": False})
        r = _fail(c, captcha="tok")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "captcha_invalid"
    # failure counter unchanged -> still captcha_required, NOT locked
    r = _fail(c)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "captcha_required"


@override_settings(HCAPTCHA_SECRET_KEY="x", CAPTCHA_ENABLED=True)
def test_captcha_gates_before_lockout(user):
    c = APIClient()
    for _ in range(3):
        _fail(c)
    # Solve captcha so failures keep counting up to the lockout threshold.
    with patch("passport.captcha.requests.post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"success": True})
        r = _fail(c, captcha="tok")  # count=4
        assert r.status_code == 401
        r = _fail(c, captcha="tok")  # count=5 -> locked
        assert r.status_code == 429
        assert r.json()["error"]["code"] == "locked"
    # Already locked -> gate skipped, returns 429 locked even without a token.
    r = _fail(c)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "locked"
