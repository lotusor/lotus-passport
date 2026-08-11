"""
Data models for Lotus Passport.

Design note:
  * PassportUser stores IDENTITY ONLY — no business fields (school, roles,
    scores). Those live in integrating apps (e.g. algo_rank), keyed by
    `passport_id`.
  * OAuthAccount binds a provider identity to a PassportUser and stores the
    provider access_token / refresh_token AES-256-CBC encrypted.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser
from django.db import models

from . import crypto

SUPPORTED_PROVIDERS = ("github", "wechat", "qq")


class PassportUserManager(BaseUserManager):
    def create_user(self, email: str | None = None, **extra: Any) -> "PassportUser":
        email = self.normalize_email(email) if email else None
        user = self.model(email=email, **extra)
        # OAuth-only login: no password by default.
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str | None = None, **extra: Any) -> "PassportUser":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        return self.create_user(email, **extra)


class PassportUser(AbstractBaseUser):
    """A unified identity. `passport_id` is the stable public identifier put in JWTs."""

    passport_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True
    )
    email = models.EmailField(unique=True, null=True, blank=True)
    nickname = models.CharField(max_length=64, blank=True, default="")
    avatar = models.URLField(blank=True, default="")
    # 身份相关扩展字段（§9.1）。school / roles 不进 passport，归接入方（§9.0）。
    username = models.CharField(max_length=64, unique=True, null=True, blank=True)
    bio = models.TextField(blank=True, default="")
    # 手机号 AES-256-CBC 加密存储（复用 crypto.encrypt_token），明文不落库。
    phone_enc = models.TextField(blank=True, default="")
    # --- 账户安全因子（§9.4a） -------------------------------------------- #
    # 密码本身复用 AbstractBaseUser 自带的 `password` 字段（Django 密码哈希器），
    # 这里只记录最近一次变更时间，供前端「上次修改于」展示。
    # 刻意不存密码强度评级：那等于给拿到库的人标出「先打这些弱口令账号」。
    password_changed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # Minimal admin flags (NOT business permissions).
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = PassportUserManager()

    class Meta:
        db_table = "passport_user"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"PassportUser({self.passport_id}) email={self.email or '—'}"

    @property
    def passport_user_id(self) -> str:
        """The claim embedded in issued JWTs and used by integrators."""
        return str(self.passport_id)

    # ---- encrypted phone accessor (§9.1) ---------------------------------- #
    @property
    def phone(self) -> str:
        if not self.phone_enc:
            return ""
        try:
            return crypto.decrypt_token(self.phone_enc)
        except Exception:  # noqa: BLE001
            return ""

    def set_phone(self, value: str | None) -> None:
        """Store phone encrypted; pass None/"" to clear."""
        self.phone_enc = crypto.encrypt_token(value) if value else ""


class OAuthAccount(models.Model):
    """A linked third-party OAuth identity for a PassportUser."""

    user = models.ForeignKey(
        PassportUser, on_delete=models.CASCADE, related_name="oauth_accounts"
    )
    provider = models.CharField(max_length=16, choices=[(p, p) for p in SUPPORTED_PROVIDERS])
    provider_user_id = models.CharField(max_length=128, help_text="openid / unionid / GitHub id")
    access_token_enc = models.TextField(blank=True, default="")
    refresh_token_enc = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "passport_oauth_account"
        unique_together = (("provider", "provider_user_id"),)
        ordering = ("provider",)

    def __str__(self) -> str:
        return f"OAuthAccount({self.provider}:{self.provider_user_id})"

    # ---- encrypted token accessors ---------------------------------------- #
    @property
    def access_token(self) -> str | None:
        return crypto.decrypt_token(self.access_token_enc) if self.access_token_enc else None

    @property
    def refresh_token(self) -> str | None:
        return crypto.decrypt_token(self.refresh_token_enc) if self.refresh_token_enc else None

    def set_tokens(self, *, access_token: str | None, refresh_token: str | None,
                   expires_at: datetime | None = None) -> None:
        self.access_token_enc = crypto.encrypt_token(access_token) if access_token else ""
        self.refresh_token_enc = crypto.encrypt_token(refresh_token) if refresh_token else ""
        self.expires_at = expires_at
        self.save(update_fields=["access_token_enc", "refresh_token_enc", "expires_at", "updated_at"])


# --------------------------------------------------------------------------- #
# Account-management models (§9.3 / §9.4d / §9.4e)
# --------------------------------------------------------------------------- #
DEVICE_TYPES = (("desktop", "桌面"), ("mobile", "手机"), ("tablet", "平板"), ("other", "其他"))


class TrustedDevice(models.Model):
    """A device the user has marked as trusted (frontend: 授权设备)."""

    user = models.ForeignKey(
        PassportUser, on_delete=models.CASCADE, related_name="trusted_devices"
    )
    name = models.CharField(max_length=128, blank=True, default="")
    device_type = models.CharField(max_length=16, choices=DEVICE_TYPES, default="other")
    os = models.CharField(max_length=64, blank=True, default="")
    browser = models.CharField(max_length=64, blank=True, default="")
    location = models.CharField(max_length=128, blank=True, default="")
    trusted = models.BooleanField(default=False)
    first_trusted_at = models.DateTimeField(null=True, blank=True)
    last_active_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "passport_trusted_device"
        ordering = ("-last_active_at",)

    def __str__(self) -> str:
        return f"TrustedDevice({self.name or self.device_type} user={self.user_id})"


class Session(models.Model):
    """An active login session, keyed by the refresh token's ``jti``.

    Lets the user list / revoke sessions (§9.4d). Revoking deletes the row and
    blacklists the ``jti`` (reusing the logout revocation path).
    """

    user = models.ForeignKey(
        PassportUser, on_delete=models.CASCADE, related_name="sessions"
    )
    jti = models.CharField(max_length=64, unique=True, db_index=True)
    device = models.CharField(max_length=64, blank=True, default="")
    device_type = models.CharField(max_length=16, choices=DEVICE_TYPES, default="other")
    os = models.CharField(max_length=64, blank=True, default="")
    browser = models.CharField(max_length=64, blank=True, default="")
    location = models.CharField(max_length=128, blank=True, default="")
    ip = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "passport_session"
        ordering = ("-last_active_at",)

    def __str__(self) -> str:
        return f"Session({self.jti[:8]} user={self.user_id})"


class LoginEvent(models.Model):
    """Immutable audit of authentication attempts (§9.4e)."""

    STATUS = (("success", "成功"), ("failed", "失败"))

    user = models.ForeignKey(
        PassportUser,
        on_delete=models.CASCADE,
        related_name="login_events",
        null=True,
        blank=True,
    )
    ip = models.CharField(max_length=64, blank=True, default="")
    location = models.CharField(max_length=128, blank=True, default="")
    user_agent = models.TextField(blank=True, default="")
    device = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=8, choices=STATUS, default="success")
    reason = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "passport_login_event"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"LoginEvent({self.status} {self.ip} user={self.user_id})"


class Passkey(models.Model):
    """A WebAuthn credential (passkey) bound to a PassportUser (§9.4b).

    Enables phishing-resistant, passwordless login. The public key (COSE/CBOR)
    is stored; the private key never leaves the user's device. ``credential_id``
    is globally unique across authenticators, so it is unique here too.
    """

    user = models.ForeignKey(
        PassportUser, on_delete=models.CASCADE, related_name="passkeys"
    )
    credential_id = models.CharField(max_length=255, unique=True, db_index=True)
    # COSE public key (CBOR) as hex — never the private key.
    public_key = models.TextField()
    sign_count = models.IntegerField(default=0)
    device_type = models.CharField(max_length=32, blank=True, default="")
    aaguid = models.CharField(max_length=36, blank=True, default="")
    transports = models.CharField(max_length=255, blank=True, default="")
    name = models.CharField(max_length=128, blank=True, default="")
    device_label = models.CharField(max_length=128, blank=True, default="")
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "passport_passkey"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Passkey({self.name or self.credential_id[:8]} user={self.user_id})"

    def to_dict(self) -> dict:
        """Serializable shape consumed by the security page (snake_case + ISO)."""
        return {
            "id": str(self.id),
            "name": self.name,
            "device": self.device_label,
            "added_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }


class AccountDeletion(models.Model):
    """Audit trail for account self-deletion (§9.4f).

    Only an anonymized reference (the ``passport_id`` UUID string) plus the
    deletion timestamp is retained — no PII (email/phone/nickname) is kept, in
    line with the "保留审计留痕（软删或匿名化 passport_id）" design. This lets
    us prove *that* an account was deleted and *when*, without retaining the
    data we just purged.
    """

    passport_id = models.CharField(max_length=36, db_index=True)
    deleted_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "passport_account_deletion"
        ordering = ("-deleted_at",)

    def __str__(self) -> str:
        return f"AccountDeletion({self.passport_id} @ {self.deleted_at})"
