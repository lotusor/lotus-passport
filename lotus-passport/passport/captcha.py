"""hCaptcha verification (security hardening §一.C).

Fail-closed: a missing token/secret or any transport error is treated as
*not passed*, so a flaky verification service can never open the login door.
The endpoint stays dormant unless ``settings.CAPTCHA_ENABLED`` is True (i.e.
``HCAPTCHA_SECRET_KEY`` is configured), so it never affects existing login
behaviour or the test suite.
"""
from __future__ import annotations

import requests
from django.conf import settings

HCAPTCHA_VERIFY_URL = "https://hcaptcha.com/siteverify"


class CaptchaVerifier:
    @staticmethod
    def verify(token: str | None, remote_ip: str | None = None) -> bool:
        secret = getattr(settings, "HCAPTCHA_SECRET_KEY", "")
        if not secret or not token:
            return False
        try:
            resp = requests.post(
                HCAPTCHA_VERIFY_URL,
                data={"secret": secret, "response": token, "remoteip": remote_ip},
                timeout=5,
            )
            return bool(resp.json().get("success"))
        except Exception:
            return False  # fail-closed
