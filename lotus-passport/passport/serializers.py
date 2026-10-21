"""
DRF serializers for account-management endpoints (§9.1 / §9.3 / §9.4d / §9.4e).
"""
from __future__ import annotations

from rest_framework import serializers

from .models import LoginEvent, PassportUser, Session, TrustedDevice


class ProfileSerializer(serializers.ModelSerializer):
    """Read/write the user's own identity profile (§9.1).

    ``email`` is intentionally read-only here — changing it must go through the
    verified email-flow (§9.4a / §9.7), not a plain PATCH.
    """

    phone = serializers.CharField(required=False, allow_blank=True, write_only=False)
    # 只读派生字段：账户是否设有可用密码。
    # 前端据此决定是否在「注销账户」弹窗中渲染密码输入框（§9.4f step-up）。
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = PassportUser
        fields = (
            "passport_user_id",
            "email",
            "username",
            "nickname",
            "avatar",
            "bio",
            "phone",
            "has_password",
        )
        read_only_fields = ("passport_user_id", "email", "has_password")

    def get_has_password(self, obj: PassportUser) -> bool:
        return obj.has_usable_password()

    def validate_username(self, value: str | None) -> str | None:
        if not value:
            return value
        # 唯一性由 DB 约束兜底；这里做长度/格式预校验，友好报错。
        if len(value) < 3 or len(value) > 64:
            raise serializers.ValidationError("用户名长度需为 3-64 个字符")
        return value

    def validate_phone(self, value: str | None) -> str | None:
        if value and (not value.isdigit() or len(value) < 6 or len(value) > 20):
            raise serializers.ValidationError("手机号格式不正确")
        return value

    def update(self, instance: PassportUser, validated: dict) -> PassportUser:
        # phone 走加密存取器，单独处理（ModelSerializer 不认识 phone_enc）。
        phone = validated.pop("phone", None)
        if "phone" in self.initial_data:  # 仅当请求显式携带 phone 字段
            instance.set_phone(phone or "")
        for attr, val in validated.items():
            setattr(instance, attr, val)
        instance.save()
        return instance


class DeviceSerializer(serializers.ModelSerializer):
    """Authorized device (§9.3)."""

    class Meta:
        model = TrustedDevice
        fields = (
            "id",
            "name",
            "device_type",
            "os",
            "browser",
            "location",
            "trusted",
            "first_trusted_at",
            "last_active_at",
        )
        read_only_fields = (
            "id",
            "device_type",
            "os",
            "browser",
            "location",
            "first_trusted_at",
            "last_active_at",
        )


class SessionSerializer(serializers.ModelSerializer):
    """Active session (§9.4d). ``current`` is injected by the view."""

    current = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Session
        fields = (
            "id",
            "jti",
            "device",
            "device_type",
            "os",
            "browser",
            "location",
            "ip",
            "created_at",
            "last_active_at",
            "current",
        )
        read_only_fields = fields


class LoginEventSerializer(serializers.ModelSerializer):
    """Login history entry (§9.4e)."""

    time = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = LoginEvent
        fields = ("id", "time", "location", "ip", "device", "status", "reason")
        read_only_fields = fields
