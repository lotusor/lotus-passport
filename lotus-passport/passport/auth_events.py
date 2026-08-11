"""
Authentication event recording (§9.3 / §9.4d / §9.4e).

Called from the login paths (OAuth callback + dev login) so every successful or
failed authentication lands in the audit tables and creates/updates a Session
row. Kept dependency-light and defensive: a failure here must never break login.
"""
from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import LoginEvent, Session, TrustedDevice
from .revocation import RevocationStore
from .geo import resolve_location

_MOBILE_RE = re.compile(r"(android|iphone|ipad|ipod|mobile|windows phone)", re.I)
_TABLET_RE = re.compile(r"(ipad|tablet|kindle|playbook)", re.I)
_BROWSER_RE = [
    ("Edg", "Edge"),
    ("OPR", "Opera"),
    ("Chrome", "Chrome"),
    ("Firefox", "Firefox"),
    ("Safari", "Safari"),
]
_OS_RE = [
    ("Windows NT", "Windows"),
    ("Mac OS X", "macOS"),
    ("Android", "Android"),
    ("iPhone OS", "iOS"),
    ("iPad", "iPadOS"),
    ("Linux", "Linux"),
]


def parse_user_agent(ua: str) -> dict[str, str]:
    """Best-effort UA → {device_type, os, browser, device}."""
    ua = ua or ""
    if _TABLET_RE.search(ua):
        dtype = "tablet"
    elif _MOBILE_RE.search(ua):
        dtype = "mobile"
    else:
        dtype = "desktop"
    os_name = "未知"
    for token, name in _OS_RE:
        if token in ua:
            os_name = name
            break
    browser = "未知"
    for token, name in _BROWSER_RE:
        if token in ua:
            browser = name
            break
    device = f"{browser} · {os_name}" if browser != "未知" or os_name != "未知" else "未知客户端"
    return {"device_type": dtype, "os": os_name, "browser": browser, "device": device}


def _client_meta(request: Any | None) -> dict[str, str]:
    if not request:
        return {"ip": "", "ua": "", "location": "未知位置"}
    ip = (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR", "")
    )
    ua = request.META.get("HTTP_USER_AGENT", "")
    # 真实地理位置：IP → 省/市（带缓存与降级，失败回退 ""）。
    location = resolve_location(ip) or "未知位置"
    return {"ip": ip, "ua": ua, "location": location}


def _enforce_session_cap(user: "Any", current_jti: str) -> None:
    """Evict the oldest sessions if the user exceeds MAX_SESSIONS_PER_USER (§一.F)."""
    max_sessions = getattr(settings, "MAX_SESSIONS_PER_USER", 0)
    if not max_sessions:
        return
    sessions = list(Session.objects.filter(user=user).order_by("created_at"))
    excess = len(sessions) - max_sessions
    if excess <= 0:
        return
    for sess in sessions[:excess]:
        if sess.jti == current_jti:
            continue
        try:
            RevocationStore().revoke(sess.jti, 60 * 60 * 24 * 14)
            sess.delete()
        except Exception:  # noqa: BLE001
            pass


def _ensure_trusted_device(user: "Any", parsed: dict[str, str], location: str) -> None:
    """首次登录按设备指纹自动写入「授权设备」并默认信任（§9.3）。

    按 (device_type, os, browser) 去重：同一台设备的重复登录只刷新 last_active_at，
    不会刷出多条。列表因此不再为空，用户可在「登录设备」页撤销 / 取消信任。
    """
    obj, created = TrustedDevice.objects.update_or_create(
        user=user,
        device_type=parsed["device_type"],
        os=parsed["os"],
        browser=parsed["browser"],
        defaults={"location": location},
    )
    if created:
        obj.name = f"{parsed['browser']} · {parsed['os']}" if (
            parsed["browser"] != "未知" or parsed["os"] != "未知"
        ) else "未知设备"
        obj.trusted = True
        obj.first_trusted_at = timezone.now()
        obj.save(update_fields=["name", "trusted", "first_trusted_at"])


def record_login_success(user: "Any", *, jti: str, request: Any | None = None) -> None:
    """Persist a successful login: Session row + LoginEvent (+ TrustedDevice)."""
    try:
        meta = _client_meta(request)
        parsed = parse_user_agent(meta["ua"])
        Session.objects.update_or_create(
            jti=jti,
            defaults={
                "user": user,
                "device": parsed["device"],
                "device_type": parsed["device_type"],
                "os": parsed["os"],
                "browser": parsed["browser"],
                "location": meta["location"],
                "ip": meta["ip"],
                "user_agent": meta["ua"],
            },
        )
        _ensure_trusted_device(user, parsed, meta["location"])
        _enforce_session_cap(user, jti)
        LoginEvent.objects.create(
            user=user,
            ip=meta["ip"],
            location=meta["location"],
            user_agent=meta["ua"],
            device=parsed["device"],
            status="success",
            reason="",
        )
    except Exception:  # noqa: BLE001 — never block login on analytics writes
        pass


def record_login_failure(*, user: "Any | None" = None, request: Any | None = None,
                         reason: str = "") -> None:
    """Persist a failed login attempt (audit only)."""
    try:
        meta = _client_meta(request)
        parsed = parse_user_agent(meta["ua"])
        LoginEvent.objects.create(
            user=user,
            ip=meta["ip"],
            location=meta["location"],
            user_agent=meta["ua"],
            device=parsed["device"],
            status="failed",
            reason=reason,
        )
    except Exception:  # noqa: BLE001
        pass


__all__ = ["parse_user_agent", "record_login_success", "record_login_failure", "TrustedDevice"]
