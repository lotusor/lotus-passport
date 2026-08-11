"""
WebAuthn / Passkey helpers (§9.4b).

Wraps py_webauthn for the registration and authentication (assertion) ceremonies.
Challenges live in Redis (TTL 300s) via WebAuthnChallengeStore: keyed by the user
for registration, and by a one-shot ``state`` token for usernameless login (where
the user is not yet known). No private key material is ever handled server-side.
"""
from __future__ import annotations

import json
import secrets
from typing import Any

from django.conf import settings
from django.utils import timezone

import webauthn as _webauthn
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .models import Passkey, PassportUser
from .ratelimit import get_redis


class WebAuthnError(Exception):
    """Raised for any ceremony failure (expired challenge, bad attestation, ...)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _rp_id() -> str:
    return getattr(settings, "PASSPORT_RP_ID", "localhost")


def _rp_name() -> str:
    return getattr(settings, "PASSPORT_RP_NAME", "莲花通行证")


def _origins() -> list[str]:
    return getattr(
        settings,
        "WEBAUTHN_ORIGINS",
        ["http://localhost:3000", "http://localhost:8000"],
    )


# Algorithms we accept for new credentials.
_ALGOS = [
    COSEAlgorithmIdentifier.ECDSA_SHA_256,
    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
    COSEAlgorithmIdentifier.EDDSA,
]


def describe_device(device_type: str, transports: list[str]) -> str:
    """Best-effort human label for the frontend PasskeySection ``device`` field."""
    t = transports or []
    if "internal" in t:
        return "本机设备 · 生物识别"
    if "usb" in t:
        return "安全密钥 · USB"
    if "nfc" in t:
        return "安全密钥 · NFC"
    if "ble" in t:
        return "安全密钥 · 蓝牙"
    if "hybrid" in t:
        return "安全密钥 · 混合"
    return "外部安全密钥" if device_type == "cross-platform" else "本机设备"


class WebAuthnChallengeStore:
    """Short-lived challenge storage. Single-use: consumed on verification."""

    PREFIX = "wa:challenge:"
    TTL = 300

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or get_redis()

    def put(self, key: str, challenge: str) -> None:
        self.client.set(f"{self.PREFIX}{key}", challenge, ex=self.TTL)

    def take(self, key: str) -> str | None:
        # Redis (and fakeredis) returns bytes; challenges are ASCII token strings.
        value = self.client.get(f"{self.PREFIX}{key}")
        if not value:
            return None
        self.client.delete(f"{self.PREFIX}{key}")
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return value


def _normalize_credential(raw: Any) -> tuple[str, dict]:
    """Return (json_string, parsed_dict) for a client response (str or dict)."""
    if isinstance(raw, str):
        return raw, json.loads(raw)
    return json.dumps(raw), raw


def build_registration_options(user: PassportUser) -> str:
    """Generate registration options JSON and persist the challenge."""
    store = WebAuthnChallengeStore()
    challenge = secrets.token_urlsafe(32)
    existing = list(
        Passkey.objects.filter(user=user).values_list("credential_id", flat=True)
    )
    options = _webauthn.generate_registration_options(
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=str(user.passport_id).encode(),
        user_name=user.email or user.username or str(user.passport_id),
        user_display_name=user.nickname or user.email or str(user.passport_id),
        challenge=challenge.encode(),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(cid))
            for cid in existing
        ],
        supported_pub_key_algs=_ALGOS,
    )
    store.put(f"reg:{user.passport_id}", challenge)
    return _webauthn.options_to_json(options)


def register_passkey(user: PassportUser, raw: Any, name: str = "") -> Passkey:
    """Verify an attestation response and persist the new passkey."""
    store = WebAuthnChallengeStore()
    expected = store.take(f"reg:{user.passport_id}")
    if not expected:
        raise WebAuthnError("挑战已过期，请重试注册")
    raw_str, parsed = _normalize_credential(raw)
    try:
        verified = _webauthn.verify_registration_response(
            credential=raw_str,
            expected_challenge=expected.encode(),
            expected_rp_id=_rp_id(),
            expected_origin=_origins(),
            supported_pub_key_algs=_ALGOS,
        )
    except WebAuthnError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any py_webauthn error as 400
        raise WebAuthnError(f"通行密钥注册校验失败：{exc}") from exc

    transports = (parsed.get("response", {}) or {}).get("transports", []) or []
    pk = Passkey.objects.create(
        user=user,
        credential_id=bytes_to_base64url(verified.credential_id),
        public_key=verified.credential_public_key.hex(),
        sign_count=verified.sign_count,
        device_type=verified.credential_device_type,
        aaguid=str(verified.aaguid),
        transports=",".join(transports),
        name=name or "通行密钥",
        device_label=describe_device(verified.credential_device_type, transports),
    )
    return pk


def build_authentication_options() -> tuple[str, str]:
    """Generate assertion options JSON and a one-shot ``state`` token."""
    store = WebAuthnChallengeStore()
    challenge = secrets.token_urlsafe(32)
    state = secrets.token_urlsafe(16)
    options = _webauthn.generate_authentication_options(
        rp_id=_rp_id(),
        challenge=challenge.encode(),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    store.put(f"auth:{state}", challenge)
    return _webauthn.options_to_json(options), state


def verify_authentication(raw: Any, state: str) -> PassportUser:
    """Verify an assertion, update the passkey, and return its owner."""
    store = WebAuthnChallengeStore()
    expected = store.take(f"auth:{state}")
    if not expected:
        raise WebAuthnError("挑战已过期，请重试登录")
    raw_str, parsed = _normalize_credential(raw)
    credential_id = parsed.get("id")
    if not credential_id:
        raise WebAuthnError("缺少凭据标识")
    pk = (
        Passkey.objects.select_related("user")
        .filter(credential_id=credential_id)
        .first()
    )
    if not pk:
        raise WebAuthnError("未知的通行密钥", status_code=401)
    try:
        verified = _webauthn.verify_authentication_response(
            credential=raw_str,
            expected_challenge=expected.encode(),
            expected_rp_id=_rp_id(),
            expected_origin=_origins(),
            credential_public_key=bytes.fromhex(pk.public_key),
            credential_current_sign_count=pk.sign_count,
        )
    except WebAuthnError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise WebAuthnError(f"通行密钥验证失败：{exc}") from exc

    pk.sign_count = verified.new_sign_count
    pk.last_used_at = timezone.now()
    pk.save(update_fields=["sign_count", "last_used_at", "updated_at"])
    return pk.user
