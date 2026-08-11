"""
Account security factors: password validation only (§9.4a).

Scope decision:
* **TOTP 2FA is intentionally removed.** The product does not ship a companion
  authenticator app, and TOTP without an app-friendly workflow provides poor
  UX. Passkeys remain as the phishing-resistant option.
* **Passwords are optional.** Most accounts are OAuth-only and carry
  ``set_unusable_password()``. Helpers here must therefore cope with a user
  that simply has no password.
"""
from __future__ import annotations

from typing import Any

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from .models import PassportUser


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def validate_new_password(password: str, user: PassportUser) -> str | None:
    """Run Django's validators plus our own floor. Returns an error or None."""
    if not password:
        return "新密码不能为空"
    if len(password) < 8:
        return "密码至少 8 位"
    has_alpha = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_alpha and has_digit):
        return "密码需同时包含字母和数字"
    try:
        password_validation.validate_password(password, user)
    except ValidationError as exc:
        return "；".join(exc.messages)
    return None


# --------------------------------------------------------------------------- #
# Step-up re-authentication
# --------------------------------------------------------------------------- #
def verify_step_up(user: PassportUser, data: Any) -> tuple[bool, str]:
    """Re-verify an already-authenticated caller before a sensitive change.

    Accepts the account password when one exists. A pure-OAuth account (no
    usable password) is allowed through with just the bearer token — demanding
    more would lock the user out of the very screens that let them add a factor.
    """
    try:
        password = str(data.get("password") or data.get("current_password") or "")
    except Exception:  # noqa: BLE001 — malformed body
        password = ""

    password_ok = bool(password) and user.has_usable_password() and user.check_password(password)

    if user.has_usable_password():
        if password_ok:
            return True, ""
        return False, "该操作需要账户密码（password）"

    # No usable password: OAuth-only account.
    return True, ""


__all__ = [
    "validate_new_password",
    "verify_step_up",
]
