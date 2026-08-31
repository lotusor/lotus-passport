"""
API views for Lotus Passport.

Endpoints
---------
GET  /api/v1/health/                         liveness probe
GET  /api/v1/oauth/<provider>/login/         start OAuth, redirect to provider
GET  /api/v1/oauth/<provider>/callback/      provider redirect target, issue JWT
GET  /api/v1/userinfo/                       identity behind Bearer JWT  (algo_rank contract)
POST /api/v1/token/refresh/                  rotate access token
GET  /api/v1/.well-known/jwks.json           public key(s) for RS256 integrators

Integration contract (see README): an integrating app receives the JWT from its
frontend, then calls /api/v1/userinfo/ to resolve `passport_user_id` and create
its local account on first sight. Passport never stores business data.
"""
from __future__ import annotations

import json
import os
import re
import time
import io
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import send_mail
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import TokenRefreshView as _SimpleJWTRefresh

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied
from django.shortcuts import get_object_or_404
from django.db import IntegrityError

from .jwt import decode_access, issue_tokens
from . import email_templates
from .auth_events import parse_user_agent
from .models import (
    AccountDeletion,
    OAuthAccount,
    PassportUser,
    Session,
    TrustedDevice,
    LoginEvent,
)
from .providers import (
    PROVIDER_LABELS,
    REGISTRY,
    get_provider,
    is_provider_configured,
)

from .ratelimit import (
    AuthCodeStore,
    EmailCodeStore,
    GenericLoginTicketStore,
    OAuthStateStore,
    PendingConsentStore,
    AccountLockout,
    PasswordResetStore,
    RateLimiter,
    check_rate_limit,
    pkce_verify,
    validate_code_challenge,
)
from .captcha import CaptchaVerifier
from .redirects import is_redirect_uri_allowed, is_external_oauth_redirect, resolve_oauth_client, _origin_of
from .revocation import RevocationStore
from .auth_events import record_login_failure, record_login_success
from .security import (
    validate_new_password,
    verify_step_up,
)
from .serializers import (
    ProfileSerializer,
    DeviceSerializer,
    SessionSerializer,
    LoginEventSerializer,
)


# --------------------------------------------------------------------------- #
# Device-trust gate (§9.3): access tokens remain valid for 30min after JWT
# signature is verified, so IsAuthenticated alone lets a revoked/untrusted
# device keep auto-logging-in until the access expires. This gate closes that
# window: every business view checks that the current UA still has a
# trusted=True TrustedDevice row, returning 401 so the frontend's existing
# `restore()`/`refresh()` 401-handler clears the local tokens and forces a
# fresh login.
# --------------------------------------------------------------------------- #
def _is_device_trusted(request) -> bool:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    parsed = parse_user_agent(request.META.get("HTTP_USER_AGENT", ""))
    return TrustedDevice.objects.filter(
        user=user,
        device_type=parsed["device_type"],
        os=parsed["os"],
        browser=parsed["browser"],
        trusted=True,
    ).exists()


class IsAuthenticatedAndTrusted(BasePermission):
    """Authenticated AND 当前 UA 在 TrustedDevice 中存在且 trusted=True。

    失败抛 NotAuthenticated (401) 而非 PermissionDenied (403)，使前端
    auth-context 的 401 兜底清 token 逻辑可以自动触发重新登录。
    """

    message = "该设备未受信任，请重新登录"

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise NotAuthenticated()
        if not _is_device_trusted(request):
            raise NotAuthenticated(self.message)
        return True


def _claims_of(raw_token) -> dict:
    """Best-effort decode of a JWT's claims (signature already verified upstream).

    Used for revocation lookups. Returns {} on any failure so the caller can
    fail open rather than blocking a request on a decode error.
    """
    if not raw_token:
        return {}
    try:
        return decode_access(str(raw_token))
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
@transaction.atomic
def link_or_create_user(identity, provider: str, raw_token: dict, expires_at):
    """Find-or-create the PassportUser + OAuthAccount for a normalized identity.

    Wrapped in a single transaction: this does up to three writes (user,
    oauth account, encrypted tokens). Without it, concurrent logins on SQLite
    interleave three separate autocommit transactions and hit
    "database is locked"; on Postgres they could leave a user row with no
    linked account if the second insert fails.

    ``select_for_update`` is deliberately not used — SQLite ignores it, and the
    unique constraint on (provider, provider_user_id) is the real guard.
    """
    acc = OAuthAccount.objects.filter(
        provider=provider, provider_user_id=identity.provider_user_id
    ).first()
    if acc is not None:
        user = acc.user
    else:
        user = None
        if identity.email:
            user = PassportUser.objects.filter(email=identity.email).first()
        if user is None:
            # create_user() sets an UNUSABLE password, so OAuth-only accounts
            # are correctly password-less (has_usable_password() == False).
            # A bare objects.create() leaves an empty string that Django treats
            # as a usable password, which would wrongly let /login/ attempt it.
            user = PassportUser.objects.create_user(
                email=identity.email,
                nickname=identity.nickname,
                avatar=identity.avatar,
            )
        acc = OAuthAccount.objects.create(
            user=user, provider=provider, provider_user_id=identity.provider_user_id
        )
    acc.set_tokens(
        access_token=raw_token.get("access_token"),
        refresh_token=raw_token.get("refresh_token"),
        expires_at=expires_at,
    )
    return user


class OAuthLinkConflict(Exception):
    """Raised when an OAuth identity is already bound to a *different* user.

    Surfaces as HTTP 409 — we must never let one account silently hijack
    another account's provider identity during the bind flow.
    """

    status_code = 409

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"该{PROVIDER_LABELS.get(provider, provider)}账号已绑定到其他用户")


def bind_existing_user(user, identity, provider: str, raw_token: dict, expires_at):
    """Attach an OAuth identity to an EXISTING, already-authenticated user (§9.2).

    Unlike :func:`link_or_create_user` this never creates a new PassportUser.
    If the provider identity is already linked to a *different* user we raise
    :class:`OAuthLinkConflict` instead of overwriting — protecting against
    account takeover. If it is already linked to THIS user we just refresh the
    tokens (idempotent re-bind).
    """
    existing = OAuthAccount.objects.filter(
        provider=provider, provider_user_id=identity.provider_user_id
    ).first()
    if existing is not None and existing.user_id != user.id:
        raise OAuthLinkConflict(provider)

    acc, _ = OAuthAccount.objects.get_or_create(
        user=user, provider=provider, provider_user_id=identity.provider_user_id
    )
    acc.set_tokens(
        access_token=raw_token.get("access_token"),
        refresh_token=raw_token.get("refresh_token"),
        expires_at=expires_at,
    )
    return user


def _user_retains_login_method(user, removing_provider: str) -> bool:
    """True if `user` would still be able to log in after dropping `removing_provider`.

    A user must keep at least one primary login method: a usable password or
    another linked OAuth account. (Passkey 已于 2026-08-27 砍除，不再计入。)
    """
    if user.has_usable_password():
        return True
    if user.oauth_accounts.exclude(provider=removing_provider).exists():
        return True
    return False


# --------------------------------------------------------------------------- #
# views
# --------------------------------------------------------------------------- #
def health_check(request):
    return JsonResponse({"status": "ok", "service": "lotus-passport"})


class OAuthLoginView(APIView):
    authentication_classes: list = []  # public endpoint
    permission_classes: list = []

    def get(self, request, provider: str):
        if not check_rate_limit(request, *settings.RATE_LIMIT_LOGIN, scope="oauth-login"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if provider not in REGISTRY:
            return Response(
                {"error": {"code": 400, "message": f"不支持的 OAuth 提供商: {provider}"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prov = get_provider(provider)
        if not is_provider_configured(provider):
            return Response(
                {
                    "error": {
                        "code": 400,
                        "message": "当前功能开发中",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        redirect_uri = self._validate_redirect(request)
        if redirect_uri is None:
            return Response(
                {
                    "error": {
                        "code": 400,
                        "message": (
                            "redirect_uri 不在允许列表中，请管理员在 "
                            "OAUTH_ALLOWED_REDIRECT_URIS 中配置该回跳地址"
                        ),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        # PKCE（RFC 7636）：带 code_challenge 的登录走「授权码 + PKCE」模式，
        # 回调只回跳一次性 code，令牌由前端用 code + code_verifier 换取
        # （POST /api/v1/oauth/token/），不再经 URL fragment 下发。
        # 不带 code_challenge 的旧前端继续走 fragment 模式（过渡兼容）。
        pair = validate_code_challenge(
            request.GET.get("code_challenge"),
            request.GET.get("code_challenge_method"),
        )
        if pair is None:
            return Response(
                {
                    "error": {
                        "code": 400,
                        "message": "code_challenge / code_challenge_method 参数无效（S256，43-128 字符）",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        challenge, challenge_method = pair
        state = OAuthStateStore().save(
            provider,
            redirect_uri,
            code_challenge=challenge or None,
            code_challenge_method=challenge_method or None,
        )
        return JsonResponse(
            {"authorize_url": prov.get_authorize_url(state)}, status=200
        )

    def _validate_redirect(self, request) -> str | None:
        """Return the validated redirect_uri, or None if it must be rejected.

        An empty redirect_uri is allowed (the caller falls back to JSON). A
        disallowed value yields None so the view can 400.
        """
        redirect_uri = request.GET.get("redirect_uri", "")
        if not is_redirect_uri_allowed(redirect_uri):
            return None
        return redirect_uri


class OAuthCallbackView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, provider: str):
        if not check_rate_limit(request, *settings.RATE_LIMIT_CALLBACK, scope="oauth-cb"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        error = request.GET.get("error")
        if error:
            return Response(
                {"error": {"code": 400, "message": f"提供商返回错误: {error}"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        code = request.GET.get("code")
        state = request.GET.get("state")
        if not code or not state:
            return Response(
                {"error": {"code": 400, "message": "缺少 code 或 state 参数"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stored = OAuthStateStore().consume(state)
        if stored is None or stored.get("provider") != provider:
            return Response(
                {"error": {"code": 400, "message": "state 无效或已过期"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prov = get_provider(provider)
        if prov is None:
            return Response(
                {"error": {"code": 400, "message": f"不支持的 OAuth 提供商: {provider}"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            raw_token, expires_at = prov.exchange_code(code)
            identity = prov.fetch_identity(raw_token)
        except Exception as exc:  # noqa: BLE001
            record_login_failure(request=request, reason="provider_comm")
            return Response(
                {"error": {"code": 502, "message": f"与提供商通信失败: {exc}"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not identity.provider_user_id:
            record_login_failure(request=request, reason="no_provider_id")
            return Response(
                {"error": {"code": 502, "message": "无法从提供商获取用户标识"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ---- account-binding mode (§9.2) ---------------------------------- #
        if stored.get("link_mode"):
            target = self._resolve_link_target(stored)
            if target is None:
                record_login_failure(request=request, reason="bind_session")
                return Response(
                    {"error": {"code": 401, "message": "绑定会话已失效，请重新发起绑定"}},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            try:
                bind_existing_user(target, identity, provider, raw_token, expires_at)
            except OAuthLinkConflict as exc:
                record_login_failure(request=request, reason="bind_conflict")
                return Response(
                    {"error": {"code": exc.status_code, "message": str(exc)}},
                    status=status.HTTP_409_CONFLICT,
                )
            frontend = stored.get("redirect_uri") or ""
            if frontend and request.GET.get("response_mode") != "json":
                if not is_redirect_uri_allowed(frontend):
                    return Response(
                        {"error": {"code": 400, "message": "redirect_uri 不在允许列表中"}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                from django.shortcuts import redirect

                return redirect(f"{frontend}?bound={provider}&status=success")
            return Response(
                {"status": "bound", "provider": provider},
                status=status.HTTP_200_OK,
            )

        # ---- normal login / signup mode ---------------------------------- #
        user = link_or_create_user(identity, provider, raw_token, expires_at)
        # aud 绑定到发起登录的应用（redirect_uri origin），接入方 SDK 配同名
        # audience 即可实现「为 A 应用签发的令牌不能在 B 应用重放」。
        frontend = stored.get("redirect_uri") or ""
        audience = _origin_of(frontend) if frontend else None
        tokens = issue_tokens(user, audience=audience)
        record_login_success(user, jti=tokens["jti"], request=request)

        # Use ONLY the redirect_uri stored in the validated OAuth state — never a
        # redirect_uri supplied directly on the callback (that would reopen the
        # open-redirect hole). Re-checked here as defence in depth.
        if frontend and request.GET.get("response_mode") != "json":
            if not is_redirect_uri_allowed(frontend):
                return Response(
                    {"error": {"code": 400, "message": "redirect_uri 不在允许列表中"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # 外部应用接入：先让用户到授权确认页确认「是否授权」，再回跳签发 token。
            # 首屏登录（redirect_uri 指向护照自己的 SPA）则跳过确认页直接回跳。
            if is_external_oauth_redirect(frontend):
                from django.shortcuts import redirect as _redirect

                ticket = PendingConsentStore().save(
                    redirect_uri=frontend,
                    access=tokens["access"],
                    refresh=tokens["refresh"],
                    token_type=tokens["token_type"],
                    passport_user_id=tokens["passport_user_id"],
                    provider=provider,
                    jti=tokens["jti"],
                    code_challenge=stored.get("code_challenge"),
                    code_challenge_method=stored.get("code_challenge_method"),
                )
                return _redirect(f"{settings.OAUTH_CONSENT_PAGE_BASE}?ticket={ticket}")

            from django.shortcuts import redirect

            # PKCE 模式：只回跳一次性授权码（query 参数），令牌由前端
            # POST /api/v1/oauth/token/ 换取，杜绝令牌进浏览器历史/Referrer。
            if stored.get("code_challenge"):
                code = AuthCodeStore().save(
                    access=tokens["access"],
                    refresh=tokens["refresh"],
                    token_type=tokens["token_type"],
                    passport_user_id=tokens["passport_user_id"],
                    code_challenge=stored.get("code_challenge"),
                    code_challenge_method=stored.get("code_challenge_method"),
                )
                return redirect(f"{frontend}?code={code}")

            # 旧 fragment 模式（过渡兼容，待接入方全部升级 PKCE 后移除）。
            frag = urlencode(
                {
                    "access_token": tokens["access"],
                    "token_type": tokens["token_type"],
                    "refresh_token": tokens["refresh"],
                    "passport_user_id": tokens["passport_user_id"],
                }
            )
            return redirect(f"{frontend}#{frag}")

        return Response(tokens, status=status.HTTP_200_OK)


    def _resolve_link_target(self, stored: dict):
        """Resolve the user a bind-flow callback should attach to.

        The passport_id was captured at bind-init time and stored inside the
        OAuth state, so even though the callback arrives unauthenticated we
        know exactly which user to enrich. Returns None if the id is gone or
        the user no longer exists (session is stale).
        """
        pid = stored.get("passport_id")
        if not pid:
            return None
        try:
            return PassportUser.objects.get(passport_id=pid)
        except PassportUser.DoesNotExist:
            return None


class OAuthConsentView(APIView):
    """OAuth 授权确认页后端（§外部应用接入）。

    外部应用（如 rank.eacm.cn）经护照完成第三方登录后，护照并不立即把 token 弹回
    应用，而是把刚签发的 token 暂存为一次性票据，并把浏览器 302 到
    ``OAUTH_CONSENT_PAGE_BASE?ticket=...``。本视图配合 account.eacm.cn 的
    ``/oauth/consent`` 页面构成「是否授权」中间页：

    * ``GET  ?ticket=...``  —— 返回申请授权的应用信息（名称 / 权限范围），供页面渲染。
    * ``POST {ticket, decision}`` —— ``decision=allow`` 时消费票据并以 fragment 回跳
      应用的 ``redirect_uri``；``decision=deny`` 时回跳应用域并带 ``oauth_error``。
      页面用原生表单提交触发本端点，后端 302 让**浏览器**真正跳转（fetch 不会跟随
      跨域 302）。
    """

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        ticket = request.GET.get("ticket")
        pending = PendingConsentStore().peek(ticket)
        if pending is None:
            return Response(
                {"error": {"code": 400, "message": "授权请求无效或已过期，请重新发起登录"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        client = resolve_oauth_client(pending["redirect_uri"])
        return Response(
            {
                "app_name": client["name"],
                "app_origin": client["origin"],
                "app_logo": client.get("logo", ""),
                "scopes": client.get("scopes", []),
                "provider": pending["provider"],
                "passport_user_id": pending["passport_user_id"],
            }
        )

    def post(self, request):
        if not check_rate_limit(request, *settings.RATE_LIMIT_CALLBACK, scope="oauth-consent"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        data = request.data or {}
        ticket = data.get("ticket") or request.GET.get("ticket")
        decision = data.get("decision")
        pending = PendingConsentStore().consume(ticket)
        if pending is None:
            return Response(
                {"error": {"code": 400, "message": "授权请求无效或已过期，请重新发起登录"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        redirect_uri = pending["redirect_uri"]
        if decision != "allow":
            # 用户拒绝：回跳应用域首页并带错误标记，由应用自行提示。
            origin = _origin_of(redirect_uri)
            from django.shortcuts import redirect

            return redirect(f"{origin}/?oauth_error=access_denied")

        from django.shortcuts import redirect

        # PKCE 模式：只回跳一次性授权码；令牌由应用前端拿 code +
        # code_verifier 到 POST /api/v1/oauth/token/ 换取。
        if pending.get("code_challenge"):
            code = AuthCodeStore().save(
                access=pending["access"],
                refresh=pending["refresh"],
                token_type=pending["token_type"],
                passport_user_id=pending["passport_user_id"],
                code_challenge=pending.get("code_challenge"),
                code_challenge_method=pending.get("code_challenge_method"),
            )
            return redirect(f"{redirect_uri}?code={code}")

        # 旧 fragment 模式（过渡兼容）。
        frag = urlencode(
            {
                "access_token": pending["access"],
                "token_type": pending["token_type"],
                "refresh_token": pending["refresh"],
                "passport_user_id": pending["passport_user_id"],
            }
        )
        return redirect(f"{redirect_uri}#{frag}")


class OAuthTokenExchangeView(APIView):
    """授权码 + PKCE 换令牌（OAuth 2.1 风格，替代 fragment 下发）。

    ``POST /api/v1/oauth/token/  {code, code_verifier}``

    授权码由登录回调（或授权确认页）生成、Redis 单次消费、TTL 120s。
    PKCE 校验失败/码无效一律 400，不区分原因（避免给攻击者探测面）。
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        if not check_rate_limit(request, *settings.RATE_LIMIT_CALLBACK, scope="oauth-token"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        data = request.data or {}
        code = (data.get("code") or "").strip()
        verifier = (data.get("code_verifier") or "").strip()
        if not code:
            return Response(
                {"error": {"code": 400, "message": "缺少 code 参数"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = AuthCodeStore().consume(code)
        if payload is None:
            return Response(
                {"error": {"code": 400, "message": "授权码无效或已过期，请重新登录"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not pkce_verify(payload.get("code_challenge"), payload.get("code_challenge_method"), verifier):
            return Response(
                {"error": {"code": 400, "message": "PKCE 校验失败，请重新发起登录"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "access": payload["access"],
                "refresh": payload["refresh"],
                "token_type": payload["token_type"],
                "passport_user_id": payload["passport_user_id"],
            },
            status=status.HTTP_200_OK,
        )


class OAuthBindView(APIView):
    """Initiate binding an OAuth provider to the CURRENT authenticated user (§9.2).

    Returns an ``authorize_url``; the browser completes the standard OAuth
    redirect and returns to the shared callback, which detects ``link_mode`` in
    the state and attaches the identity to this user instead of creating one.
    """

    permission_classes = [IsAuthenticatedAndTrusted]

    def post(self, request, provider: str):
        if not check_rate_limit(request, *settings.RATE_LIMIT_LOGIN, scope="oauth-bind"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if provider not in REGISTRY:
            return Response(
                {"error": {"code": 400, "message": f"不支持的 OAuth 提供商: {provider}"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not is_provider_configured(provider):
            return Response(
                {
                    "error": {
                        "code": 400,
                        "message": "当前功能开发中",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Early reject: already bound to THIS user (no need to round-trip).
        if request.user.oauth_accounts.filter(provider=provider).exists():
            return Response(
                {
                    "error": {
                        "code": 409,
                        "message": f"该{PROVIDER_LABELS.get(provider, provider)}账号已绑定到当前用户",
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        redirect_uri = self._validate_redirect(request)
        if redirect_uri is None:
            return Response(
                {
                    "error": {
                        "code": 400,
                        "message": (
                            "redirect_uri 不在允许列表中，请管理员在 "
                            "OAUTH_ALLOWED_REDIRECT_URIS 中配置该回跳地址"
                        ),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        prov = get_provider(provider)
        state = OAuthStateStore().save(
            provider,
            redirect_uri,
            link_mode=True,
            passport_id=str(request.user.passport_id),
        )
        return Response(
            {"authorize_url": prov.get_authorize_url(state)}, status=status.HTTP_200_OK
        )

    def _validate_redirect(self, request) -> str | None:
        redirect_uri = request.GET.get("redirect_uri", "")
        if not is_redirect_uri_allowed(redirect_uri):
            return None
        return redirect_uri


class OAuthUnbindView(APIView):
    """Remove a linked OAuth provider from the CURRENT user (§9.2).

    Refuses to leave the account with no login method (password / another
    OAuth account). Passkey 已砍除、TOTP 已去范围，均不计入。
    """

    permission_classes = [IsAuthenticatedAndTrusted]

    def delete(self, request, provider: str):
        if provider not in REGISTRY:
            return Response(
                {"error": {"code": 400, "message": f"不支持的 OAuth 提供商: {provider}"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        acc = request.user.oauth_accounts.filter(provider=provider).first()
        if acc is None:
            return Response(
                {
                    "error": {
                        "code": 404,
                        "message": f"未绑定 {PROVIDER_LABELS.get(provider, provider)}",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        if not _user_retains_login_method(request.user, provider):
            return Response(
                {
                    "error": {
                        "code": 409,
                        "message": "解绑后账号将无任何登录方式，请先设置密码或绑定其他登录方式",
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )
        acc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OAuthAccountsView(APIView):
    """List the OAuth providers linked to the CURRENT user (§9.2)."""

    permission_classes = [IsAuthenticatedAndTrusted]

    def get(self, request):
        rows = [
            {
                "provider": acc.provider,
                "label": PROVIDER_LABELS.get(acc.provider, acc.provider),
                "linked_at": acc.created_at.isoformat(),
            }
            for acc in request.user.oauth_accounts.all()
        ]
        return Response({"accounts": rows}, status=status.HTTP_200_OK)


class UserInfoView(APIView):
    """Return the verified identity for a Bearer JWT.

    This is the contract integrating apps (e.g. algo_rank) call. It returns ONLY
    identity — business fields must be resolved downstream.
    """

    # §9.3 access-token trust gate: a revoked/untrusted device's 30-min JWT is
    # otherwise still accepted here, letting it auto-login. The gate forces a
    # 401 so the frontend `restore()` clears the local tokens and re-auths.
    permission_classes = [IsAuthenticatedAndTrusted]

    def get(self, request):
        user: PassportUser = request.user
        if not user or not user.is_authenticated:
            return Response(
                {"error": {"code": 401, "message": "未认证"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        # Server-side revocation: reject a token whose jti is blacklisted via
        # /api/v1/logout/. Offline-verifying integrators are unaffected (they
        # re-check on expiry). Degrades open if Redis/decoding fails.
        if getattr(settings, "TOKEN_REVOCATION_ENABLED", True) and request.auth:
            jti = _claims_of(request.auth).get("jti")
            if jti and RevocationStore().is_revoked(jti):
                return Response(
                    {"error": {"code": 401, "message": "令牌已失效，请重新登录"}},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
        providers = list(user.oauth_accounts.values_list("provider", flat=True))
        return Response(build_userinfo(user, providers))


def _device_owner_for_refresh(raw: str) -> "PassportUser | None":
    """Resolve the refresh token's owner WITHOUT validating the signature.

    Returns None when the token is missing / undecodable / unknown so the
    built-in simplejwt validation still runs and returns its own 400/401.
    """

    if not raw:
        return None
    try:
        token = RefreshToken(raw)
    except Exception:  # noqa: BLE001
        return None
    uid = token.get("user_id")
    if uid is None:
        return None
    try:
        return PassportUser.objects.get(id=uid)
    except PassportUser.DoesNotExist:
        return None


def _device_blocks_refresh(user: "PassportUser", request) -> bool:
    """True when the requesting device is an *untrusted* device for `user`.

    A device the user has explicitly untrusted (§9.3) must not be silently
    auto-logged-in via the refresh token — it has to re-authenticate. Match by
    the same UA fingerprint used to dedupe TrustedDevice rows. Devices with no
    recorded row (tracking never ran) are NOT blocked, so we never lock a user
    out by accident.
    """

    parsed = parse_user_agent(request.META.get("HTTP_USER_AGENT", ""))
    return TrustedDevice.objects.filter(
        user=user,
        device_type=parsed["device_type"],
        os=parsed["os"],
        browser=parsed["browser"],
        trusted=False,
    ).exists()


class TokenRefreshView(_SimpleJWTRefresh):
    """Rotate an access token from a refresh token, gated on device trust (§9.3).

    An untrusted device's refresh is rejected with 401 so the client is forced
    to re-authenticate instead of being auto-logged-in. Trusted / unrecorded
    devices refresh normally.
    """

    def post(self, request, *args, **kwargs):
        raw = (
            request.data.get("refresh") or request.data.get("refresh_token") or ""
        ).strip()
        owner = _device_owner_for_refresh(raw)
        if owner is not None and _device_blocks_refresh(owner, request):
            return Response(
                {"error": {"code": 401, "message": "该设备未受信任，请重新登录"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    """Revoke the caller's tokens server-side (real logout / force sign-out).

    Requires a Bearer access token. Blacklists that token's ``jti`` (enforced at
    /api/v1/userinfo/) and, optionally, a ``refresh_token`` supplied in the JSON
    body — revoking the refresh kills the whole session, not just the access.
    Each blacklist entry keeps a TTL equal to the token's remaining lifetime so
    the Redis set stays tiny. The store degrades open if Redis is unavailable
    (logout still returns 200, revocation is just best-effort).
    """

    def post(self, request):
        if not request.user or not request.user.is_authenticated or not request.auth:
            return Response(
                {"error": {"code": 401, "message": "未认证"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        store = RevocationStore()
        revoked_any = False

        # Access token (from the Authorization header).
        access_claims = _claims_of(request.auth)
        access_jti = access_claims.get("jti")
        if access_jti:
            ttl = max(1, int(access_claims.get("exp", 0) - time.time()))
            revoked_any = store.revoke(access_jti, ttl) or revoked_any

        # Optional refresh token in the body — revoke the whole session too.
        try:
            refresh = (request.data.get("refresh_token") or "").strip()
        except Exception:  # noqa: BLE001
            refresh = ""
        if refresh:
            try:
                r_claims = RefreshToken(refresh).payload
                r_jti = r_claims.get("jti")
                if r_jti:
                    r_ttl = max(1, int(r_claims.get("exp", 0) - time.time()))
                    revoked_any = store.revoke(r_jti, r_ttl) or revoked_any
            except Exception:  # noqa: BLE001
                pass

        return Response(
            {"revoked": bool(revoked_any), "detail": "已登出"},
            status=status.HTTP_200_OK,
        )


# --------------------------------------------------------------------------- #
# Account-management views (§9.1 / §9.3 / §9.4d / §9.4e)
# --------------------------------------------------------------------------- #
class ProfileView(APIView):
    """GET own profile; PATCH editable identity fields (§9.1)."""

    permission_classes = [IsAuthenticatedAndTrusted]

    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    def patch(self, request):
        ser = ProfileSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        try:
            ser.save()
        except IntegrityError:
            return Response(
                {"error": {"code": 409, "message": "用户名已被占用"}},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(ProfileSerializer(request.user).data)

    def delete(self, request):
        """Self-deletion (§9.4f). Irreversible — requires explicit confirm + step-up.

        Safety model (decided 2026-08-08):
        * ``confirm=true`` is ALWAYS required (explicit acknowledgment of an
          irreversible action).
        * Accounts WITH a usable password must also supply the correct
          ``current_password`` (step-up).
        * Pure-OAuth accounts (no password) are cleared with ``confirm`` alone —
          this matches the existing ``verify_step_up`` posture where an
          already-authenticated bearer is sufficient for sensitive ops.
        * Pre-deletion resource check (§9.4f "未了结资源"): the OAuth-Client
          subsystem (§9.5) is NOT built yet, so there is nothing to reconcile.
          When §9.5 lands, this must reject accounts that still own a client
          (or require transfer) before deletion.
        """
        user: PassportUser = request.user
        if not user or not user.is_authenticated:
            return Response(
                {"error": {"code": 401, "message": "未认证"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        body = request.data or {}
        confirm = body.get("confirm")
        if not _truthy(confirm):
            return Response(
                {"error": {"code": 400, "message": "请先确认注销操作（confirm=true）"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.has_usable_password():
            pw = str(body.get("current_password") or "")
            if not user.check_password(pw):
                return Response(
                    {"error": {"code": 400, "message": "该操作需要账户密码（password）"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            _delete_user_account(user, request)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _truthy(value) -> bool:
    """Accept bool True, "true"/"1"/"yes" (case-insensitive) as confirmation."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _remove_avatar_file(avatar_url: str) -> None:
    """Best-effort removal of a locally-stored avatar before the user row dies.

    Only touches paths under MEDIA_URL (uploaded avatars); external/OAuth avatar
    URLs are left untouched. Failures are swallowed — orphaned files are a
    cosmetic issue, never a reason to abort a deletion.
    """
    if not avatar_url or not avatar_url.startswith(getattr(settings, "MEDIA_URL", "/media/")):
        return
    rel = avatar_url[len(settings.MEDIA_URL):]
    if not rel:
        return
    try:
        if default_storage.exists(rel):
            default_storage.delete(rel)
    except Exception:  # noqa: BLE001
        pass


def _delete_user_account(user: PassportUser, request) -> None:
    """Cascade-purge a user and write an anonymized deletion audit row.

    Order matters: audit first (so we always have a record even if a later
    step raises), then best-effort avatar cleanup, then related rows, then the
    user itself (FKs are CASCADE, so explicit deletes are belt-and-suspenders).
    """
    # 1) Anonymized audit trail (no PII retained).
    AccountDeletion.objects.create(passport_id=str(user.passport_id))

    # 2) Revoke every active session (jti blacklist) so offline-verifying
    #    integrators stop trusting the deleted identity once tokens expire.
    store = RevocationStore()
    session_ttl = 14 * 24 * 3600  # ~refresh TTL magnitude
    for sess in user.sessions.all():
        if sess.jti:
            store.revoke(sess.jti, session_ttl)
    claims = _claims_of(getattr(request, "auth", None))
    cur_jti = claims.get("jti")
    if cur_jti:
        store.revoke(cur_jti, max(1, int(claims.get("exp", 0) - time.time())))

    # 3) Best-effort avatar file removal, then related rows.
    _remove_avatar_file(user.avatar)
    user.oauth_accounts.all().delete()
    user.trusted_devices.all().delete()
    user.login_events.all().delete()
    user.sessions.all().delete()

    # 4) The user themselves.
    user.delete()


def build_userinfo(user: PassportUser, providers=None) -> dict:
    """构造 /api/v1/userinfo/ 返回的身份契约（algo_rank 等集成方依赖）。

    抽成公共函数，供 UserInfoView 与 AvatarUploadView 复用，保证返回字段一致。
    """
    if providers is None:
        providers = list(user.oauth_accounts.values_list("provider", flat=True))
    return {
        "passport_user_id": user.passport_user_id,
        "email": user.email or "",
        "username": user.username or "",
        "nickname": user.nickname,
        "avatar": user.avatar,
        "bio": user.bio,
        "providers": providers,
        "is_active": user.is_active,
    }


# 头像上传约束（§9.1 资料）
AVATAR_MAX_BYTES = 128 * 1024
AVATAR_MAX_DIM = 256
AVATAR_ALLOWED = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


class AvatarUploadView(APIView):
    """本地头像上传（§9.1）。

    POST multipart/form-data，字段名 ``file``。服务端再次校验类型与大小，
    用 Pillow 确认是真实图像并缩放到 AVATAR_MAX_DIM 内、重压到 ≤128KB，
    存到 MEDIA_ROOT/avatars/，删除旧本地头像，回写 user.avatar（相对 URL）。
    成功返回 build_userinfo（含最新 avatar）。avatar 仍是 URLField，无表结构变更。
    """

    permission_classes = [IsAuthenticatedAndTrusted]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"error": {"code": 400, "message": "缺少文件字段 file"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size > AVATAR_MAX_BYTES:
            return Response(
                {
                    "error": {
                        "code": 413,
                        "message": f"头像不能超过 {AVATAR_MAX_BYTES // 1024}KB",
                    }
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        ext = AVATAR_ALLOWED.get(getattr(upload, "content_type", ""))
        if not ext:
            return Response(
                {
                    "error": {
                        "code": 415,
                        "message": "仅支持 JPG / PNG / WebP / GIF 图片",
                    }
                },
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

        try:
            img = Image.open(upload)
            img.verify()  # 先确认是合法图像（不读像素）
            upload.seek(0)
            img = Image.open(upload)
            # 防解压炸弹：限制源图像素（128KB 高压缩图可解出数亿像素撑爆内存）
            if img.width * img.height > 24_000_000:  # 约 6000x4000
                return Response(
                    {"error": {"code": 413, "message": "图片分辨率过高"}},
                    status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
            img = img.convert("RGBA")
        except Exception:  # noqa: BLE001
            return Response(
                {"error": {"code": 415, "message": "图片文件已损坏或无法解析"}},
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

        # 缩放到方形（居中裁切），保持清晰又不占空间
        img = _crop_square(img)
        img.thumbnail((AVATAR_MAX_DIM, AVATAR_MAX_DIM), Image.LANCZOS)

        # 文件名：用户短 ID + uuid，避免碰撞与泄露顺序
        short_id = request.user.passport_user_id[:8]
        fname = f"avatars/{short_id}_{uuid.uuid4().hex}.png"
        full = os.path.join(settings.MEDIA_ROOT, fname)

        # 删除上一张本地头像（仅当是本站 media 路径，外部 URL 不动）
        _delete_old_avatar(request.user.avatar)

        buf = _encode_under_budget(img, AVATAR_MAX_BYTES)
        default_storage.save(fname, File(buf, name=fname))
        # 存相对 URL（MEDIA_URL 以 "media/" 结尾，这里拼出 /media/avatars/...）
        rel = settings.MEDIA_URL.rstrip("/") + "/" + fname
        request.user.avatar = rel
        request.user.save(update_fields=["avatar"])

        return Response(build_userinfo(request.user))


def _crop_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    if w == h:
        return img
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def _encode_under_budget(img: Image.Image, budget: int) -> io.BytesIO:
    """重压 PNG，必要时回退到 JPEG，确保落盘 <= budget 字节。"""
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    if out.tell() <= budget:
        out.seek(0)
        return out
    # PNG 仍超预算 → 转 JPEG（有损但体积小），逐级降质
    rgb = img.convert("RGB")
    quality = 85
    while quality >= 40:
        out = io.BytesIO()
        rgb.save(out, format="JPEG", quality=quality, optimize=True)
        if out.tell() <= budget:
            break
        quality -= 15
    out.seek(0)
    return out


def _delete_old_avatar(avatar: str) -> None:
    if not avatar or not avatar.startswith(settings.MEDIA_URL):
        return
    rel = avatar[len(settings.MEDIA_URL):].lstrip("/")
    try:
        if default_storage.exists(rel):
            default_storage.delete(rel)
    except Exception:  # noqa: BLE001
        pass


def _owner_queryset(request, model):
    """Filter a user-scoped model to the caller (object-level ownership)."""
    return model.objects.filter(user=request.user)


class DeviceListView(APIView):
    """List the user's authorized devices (§9.3)."""

    permission_classes = [IsAuthenticatedAndTrusted]

    def get(self, request):
        devices = _owner_queryset(request, TrustedDevice)
        return Response(DeviceSerializer(devices, many=True).data)


class DeviceDetailView(APIView):
    """Rename / (un)trust / remove an authorized device (§9.3)."""

    permission_classes = [IsAuthenticatedAndTrusted]

    def _get(self, request, pk: int) -> TrustedDevice:
        dev = get_object_or_404(_owner_queryset(request, TrustedDevice), pk=pk)
        return dev

    def patch(self, request, pk: int):
        dev = self._get(request, pk)
        ser = DeviceSerializer(dev, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        new_trusted = ser.validated_data.get("trusted")
        # 首次标记为信任时记录时间
        if new_trusted and not dev.trusted:
            dev.first_trusted_at = timezone.now()
        # 取消信任：立即注销该设备的全部会话，下次访问需重新验证（§9.3）
        if new_trusted is False and dev.trusted:
            _revoke_device_sessions(request.user, dev)
        ser.save()
        return Response(DeviceSerializer(dev).data)

    def delete(self, request, pk: int):
        dev = self._get(request, pk)
        # 撤销设备同时注销其全部会话，使其立即下线（§9.3）
        _revoke_device_sessions(request.user, dev)
        dev.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _current_jti(request) -> str | None:
    return _claims_of(request.auth).get("jti") if request.auth else None


class SessionListView(APIView):
    """List active sessions; DELETE revokes all *other* sessions (§9.4d)."""

    permission_classes = [IsAuthenticatedAndTrusted]

    def get(self, request):
        current = _current_jti(request)
        sessions = _owner_queryset(request, Session)
        data = SessionSerializer(sessions, many=True).data
        for row in data:
            row["current"] = row["jti"] == current
        # 把当前会话排到最前
        data.sort(key=lambda r: not r["current"])
        return Response(data)

    def delete(self, request):
        current = _current_jti(request)
        revoked = 0
        for sess in _owner_queryset(request, Session):
            if sess.jti == current:
                continue
            if _revoke_session(sess):
                revoked += 1
        return Response({"revoked": revoked, "detail": "已注销其它会话"})


class SessionDetailView(APIView):
    """Revoke a single session (§9.4d)."""

    permission_classes = [IsAuthenticatedAndTrusted]

    def delete(self, request, pk: int):
        sess = get_object_or_404(_owner_queryset(request, Session), pk=pk)
        if sess.jti == _current_jti(request):
            return Response(
                {"error": {"code": 400, "message": "不能注销当前会话"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _revoke_session(sess)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _revoke_session(sess: Session) -> bool:
    """Delete the session row and best-effort blacklist its jti (reuse logout).

    The DB row deletion is the *authoritative* logout: it removes the device's
    active session immediately. The Redis blacklist only hardens offline-
    verifying integrators and may be skipped if Redis is slow/unavailable — so
    we delete first and blacklist afterwards. A missing session already blocks
    our own refresh path, so logout must never depend on Redis succeeding.
    """
    jti = sess.jti
    sess.delete()
    try:
        RevocationStore().revoke(jti, 60 * 60 * 24 * 14)
    except Exception:  # noqa: BLE001  (best-effort; socket_timeout bounds it)
        pass
    return True


def _revoke_device_sessions(user: "PassportUser", dev: "TrustedDevice") -> int:
    """Log a device out everywhere: blacklist + delete every Session whose UA

    fingerprint matches `dev` (same dedup key as TrustedDevice). Used when a
    device is untrusted or revoked so the change takes effect immediately (§9.3).
    """

    revoked = 0
    for sess in Session.objects.filter(
        user=user,
        device_type=dev.device_type,
        os=dev.os,
        browser=dev.browser,
    ):
        if _revoke_session(sess):
            revoked += 1
    return revoked


class LoginHistoryView(APIView):
    """Recent login attempts for the user (§9.4e)."""

    permission_classes = [IsAuthenticatedAndTrusted]

    def get(self, request):
        events = _owner_queryset(request, LoginEvent)[:50]
        return Response(LoginEventSerializer(events, many=True).data)


# --------------------------------------------------------------------------- #
# Account security factors (§9.4a 密码 / §9.4c TOTP 2FA)
# --------------------------------------------------------------------------- #
def _revoke_other_sessions(user: "PassportUser", current_jti: str | None = None) -> int:
    """Revoke every session row for `user` except `current_jti` (§9.4d).

    Used after a password change so a stolen password can't keep riding an old
    session. The current session is preserved so the caller isn't logged out
    mid-operation.
    """
    revoked = 0
    for sess in Session.objects.filter(user=user):
        if current_jti and sess.jti == current_jti:
            continue
        if _revoke_session(sess):
            revoked += 1
    return revoked


def _bad_credentials() -> Response:
    return Response(
        {"error": {"code": 401, "message": "账号或密码不正确"}},
        status=status.HTTP_401_UNAUTHORIZED,
    )


class PasswordLoginView(APIView):
    """Password login (§9.4a).

    Public endpoint parallel to the OAuth login. Identifies the user by email
    OR username. A pure-OAuth account (no usable password) gets a uniform 401
    here, so password login never leaks which accounts are OAuth-only.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        identifier = (request.data.get("identifier") or "").strip()
        password = str(request.data.get("password") or "")
        captcha_token = (request.data.get("captcha") or "") or None

        # 1) Per-account rate limit — keyed on the identifier, NOT the raw IP,
        #    so hundreds of users behind one NAT IP are counted independently.
        if not check_rate_limit(
            request, *settings.RATE_LIMIT_LOGIN, scope="pwd-login", identifier=identifier or None
        ):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        # 2) Coarse per-IP edge limit — protects the server, not a single account.
        if not check_rate_limit(request, *settings.RATE_LIMIT_GLOBAL_IP, scope="ip-coarse"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        ident_key = identifier.lower() if identifier else ""
        # 3) Account lockout: block outright once the failure threshold is hit.
        lockout = AccountLockout()
        if ident_key and lockout.is_locked(ident_key, threshold=settings.ACCOUNT_LOCKOUT_THRESHOLD):
            ttl = max(lockout.ttl(ident_key), 0)
            return Response(
                {
                    "error": {
                        "code": "locked",
                        "message": f"密码错误次数过多，账户已锁定，请于 {ttl // 60} 分钟后重试",
                        "retry_after": ttl,
                    }
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # 4) CAPTCHA gate: only when enabled AND this account has already hit
        #    the failure threshold AND it is not locked (lockout wins above).
        #    A missing/invalid token neither consumes the failure counter nor
        #    locks the account — it just blocks this attempt.
        if settings.CAPTCHA_ENABLED and ident_key:
            prior_failures = lockout.failures(ident_key)
            if prior_failures >= settings.CAPTCHA_TRIGGER_THRESHOLD:
                if not captcha_token:
                    return Response(
                        {
                            "error": {
                                "code": "captcha_required",
                                "message": "请完成人机验证后再试",
                            }
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not CaptchaVerifier.verify(captcha_token, request.META.get("REMOTE_ADDR")):
                    return Response(
                        {
                            "error": {
                                "code": "captcha_invalid",
                                "message": "人机验证失败，请重试",
                            }
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        user = None
        if identifier:
            if "@" in identifier:
                user = PassportUser.objects.filter(email__iexact=identifier).first()
            else:
                user = PassportUser.objects.filter(username=identifier).first()
        if (
            user is None
            or not user.has_usable_password()
            or not user.check_password(password)
        ):
            record_login_failure(request=request, reason="bad_credentials")
            if ident_key:
                count, ttl = lockout.register_failure(
                    ident_key,
                    threshold=settings.ACCOUNT_LOCKOUT_THRESHOLD,
                    window=settings.ACCOUNT_LOCKOUT_WINDOW,
                )
                if count >= settings.ACCOUNT_LOCKOUT_THRESHOLD:
                    return Response(
                        {
                            "error": {
                                "code": "locked",
                                "message": f"密码错误次数过多，账户已锁定，请于 {ttl // 60} 分钟后重试",
                                "retry_after": ttl,
                            }
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )
                if count >= settings.CAPTCHA_TRIGGER_THRESHOLD:
                    # Tell the frontend to render the widget immediately after
                    # this failure, so the user isn't forced into an extra
                    # attempt just to discover the captcha is now required.
                    r = _bad_credentials()
                    r.data["error"]["captcha_required"] = True
                    return r
            return _bad_credentials()

        # Success: clear any failure counter so a past lockout can't stick around.
        if ident_key:
            lockout.clear(ident_key)
        tokens = issue_tokens(user)
        record_login_success(user, jti=tokens["jti"], request=request)
        return Response(tokens, status=status.HTTP_200_OK)


class PasswordStatusView(APIView):
    """Report whether the account has a password set (§9.4a)."""

    permission_classes = [IsAuthenticatedAndTrusted]

    def get(self, request):
        user = request.user
        return Response(
            {
                "has_password": user.has_usable_password(),
                "password_changed_at": (
                    user.password_changed_at.isoformat() if user.password_changed_at else None
                ),
            }
        )


class PasswordChangeView(APIView):
    """Set or change the account password (§9.4a).

    * OAuth-only accounts (no usable password) set one for the first time with
      no ``current_password`` — that IS the step-up for an account whose only
      credential is the bearer token.
    * Password accounts must supply ``current_password`` — verified via
      ``verify_step_up``.
    * On success every OTHER session is revoked (§9.4d) so a compromised
      password can't keep a foothold.
    """

    permission_classes = [IsAuthenticatedAndTrusted]

    def post(self, request):
        user = request.user
        new_password = str(request.data.get("new_password") or "")

        ok, err = verify_step_up(
            user,
            {
                "password": str(request.data.get("current_password") or ""),
            },
        )
        if not ok:
            return Response(
                {"error": {"code": 400, "message": err}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        err = validate_new_password(new_password, user)
        if err:
            return Response(
                {"error": {"code": 400, "message": err}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.password_changed_at = timezone.now()
        user.save()
        _revoke_other_sessions(user, _current_jti(request))
        return Response(
            {
                "has_password": True,
                "password_changed_at": user.password_changed_at.isoformat(),
                "detail": "密码已更新，其它会话已注销",
            }
        )


# --------------------------------------------------------------------------- #
# Password reset via email (§9.4a reset，2026-08-27)
#
# 零成本方案：免费 SMTP（QQ 邮箱授权码 / Resend 免费层）+ Redis 一次性 token。
# 未配置 EMAIL_HOST 时整体 503（诚实报错，不假装已发送）；已配置时对
# 存在/不存在的 identifier 统一返回 200（防账户枚举）。
# --------------------------------------------------------------------------- #
def _resolve_identifier(identifier: str) -> "PassportUser | None":
    """Resolve email OR username to a user — mirrors PasswordLoginView."""
    if not identifier:
        return None
    if "@" in identifier:
        return PassportUser.objects.filter(email__iexact=identifier).first()
    return PassportUser.objects.filter(username=identifier).first()


class PasswordResetRequestView(APIView):
    """``POST /api/v1/security/password/reset-request/  {identifier}``

    Sends a one-time reset link (30 min TTL) when the account exists and has
    an email. Always answers 200 with a generic message so the endpoint cannot
    be used to enumerate accounts; 503 when SMTP is not configured.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        identifier = (request.data.get("identifier") or "").strip()
        if not check_rate_limit(
            request, *settings.RATE_LIMIT_LOGIN, scope="pw-reset", identifier=identifier or None
        ):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not check_rate_limit(request, *settings.RATE_LIMIT_GLOBAL_IP, scope="ip-coarse"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not settings.PASSWORD_RESET_ENABLED:
            return Response(
                {
                    "error": {
                        "code": 503,
                        "message": (
                            "邮件服务未配置，暂时无法自助找回密码。"
                            "已绑定 GitHub/QQ 的用户可直接用第三方登录后在账户安全页重设密码。"
                        ),
                    }
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        user = _resolve_identifier(identifier)
        sent = False
        if user is not None and user.email:
            token = PasswordResetStore(ttl=settings.PASSWORD_RESET_TOKEN_TTL).save(user.pk)
            link = f"{settings.PASSWORD_RESET_FRONTEND_URL}?token={token}"
            minutes = settings.PASSWORD_RESET_TOKEN_TTL // 60
            html, text = email_templates.link_email(
                "重置你的密码",
                link,
                "重置密码",
                "你（或他人）刚刚请求重置莲花通行证密码。",
                minutes=minutes,
            )
            try:
                send_mail(
                    subject="【莲花通行证】重置你的密码",
                    message=text,
                    html_message=html,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                sent = True
            except Exception:  # noqa: BLE001 — SMTP 故障不向调用方暴露细节
                sent = False

        # 防枚举：存在/不存在/发送失败 一律同一句 200 文案，且不携带任何
        # 可区分字段（曾暴露 sent 布尔值，被用于枚举注册邮箱）。
        return Response(
            {
                "detail": "如果该账户存在且绑定了邮箱，重置邮件已发送，请注意查收（含垃圾邮件箱）。",
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """``POST /api/v1/security/password/reset/  {token, new_password}``

    Consumes the one-time token, sets the new password and revokes EVERY
    session (a reset usually means the old password was compromised).
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        new_password = str(request.data.get("new_password") or "")
        if not check_rate_limit(request, *settings.RATE_LIMIT_GLOBAL_IP, scope="ip-coarse"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not token:
            return Response(
                {"error": {"code": 400, "message": "缺少 token 参数"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        uid = PasswordResetStore(ttl=settings.PASSWORD_RESET_TOKEN_TTL).consume(token)
        if uid is None:
            return Response(
                {"error": {"code": 400, "message": "重置链接无效或已过期，请重新发起找回密码"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            user = PassportUser.objects.get(pk=uid)
        except PassportUser.DoesNotExist:
            return Response(
                {"error": {"code": 400, "message": "重置链接无效或已过期，请重新发起找回密码"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        err = validate_new_password(new_password, user)
        if err:
            return Response(
                {"error": {"code": 400, "message": err}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(new_password)
        user.password_changed_at = timezone.now()
        user.save()
        # 重置成功 = 旧密码视为已泄露：吊销该用户全部会话（含离线 jti 黑名单）。
        for sess in list(Session.objects.filter(user=user)):
            _revoke_session(sess)
        return Response(
            {"detail": "密码已重置，请使用新密码重新登录"},
            status=status.HTTP_200_OK,
        )


# --------------------------------------------------------------------------- #
# Email verification codes (2026-08-27)：登录即注册 / 首次绑定邮箱 / 更改邮箱
#
# 验证码收件箱语义（与用户两轮确认，最终规则：**新邮箱必须独立验证**）：
#   * 登录/注册（purpose=login）：码发给登录用邮箱本身；
#   * 首次绑定（purpose=bind）：码发给**目标新邮箱**（一重验证：邮箱所有权）；
#   * 更改邮箱（双重验证，两码都通过才换绑）：
#       - purpose=new：码发给**新邮箱**（证明“你拥有新邮箱”）；
#       - purpose=old：码发给**旧邮箱**（证明“你是账号主人”）；
# 所有码均为 6 位数字、10 分钟有效、单次消费、错 5 次作废（EmailCodeStore）。
# 发送频率：60s / 邮箱 / purpose + 10 次 / 小时（防轰炸），未配 SMTP 时整体 503。
# --------------------------------------------------------------------------- #
# 各 purpose 的邮件文案（subject, 场景说明行）。验证码本身由模板渲染。
_EMAIL_CODE_COPY = {
    "login": ("你的莲花通行证登录验证码", "你正在进行邮箱验证码登录"),
    "bind": ("绑定你的莲花通行证邮箱", "你正在为莲花通行证账户绑定此邮箱"),
    "new": ("验证你的新邮箱", "你正在将莲花通行证账户邮箱更改为此邮箱"),
    "old": ("确认更改莲花通行证邮箱", "你正在更改莲花通行证账户邮箱，请确认是本人操作"),
}


def _send_email_code(request, email: str, purpose: str) -> tuple[bool, str]:
    """发送验证码邮件（带频率限制，HTML 模板美化）。返回 (ok, error_message)。"""
    if not settings.PASSWORD_RESET_ENABLED:  # 同一开关：EMAIL_HOST 未配置
        return False, "邮件服务未配置，暂时无法发送验证码"
    # 频率：同邮箱同 purpose 60s 一次
    if not RateLimiter().is_allowed(f"emailcode:send:{purpose}:{email.lower()}", 1, 60):
        return False, "发送过于频繁，请 1 分钟后再试"
    # 频率：同邮箱每小时最多 10 条（跨 purpose 合计）
    if not RateLimiter().is_allowed(f"emailcode:hourly:{email.lower()}", 10, 3600):
        return False, "该邮箱发送次数已达每小时上限，请稍后再试"
    code = EmailCodeStore().save(email, purpose)
    subject, purpose_line = _EMAIL_CODE_COPY[purpose]
    html, text = email_templates.code_email(subject, code, purpose_line)
    try:
        send_mail(
            subject=f"【莲花通行证】{subject}",
            message=text,
            html_message=html,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 — SMTP 故障不暴露细节
        return False, "邮件发送失败，请稍后重试"
    return True, ""


def _valid_new_email(email: str | None) -> str | None:
    """校验邮箱格式；返回规范化邮箱或 None。"""
    if not email:
        return None
    email = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return None
    return email


class EmailCodeSendView(APIView):
    """``POST /api/v1/security/email/send-code/  {email, purpose}``

    purpose:
      * ``login``（公开）：登录/注册，码发登录邮箱本身；
      * ``bind``（需登录+无邮箱）：首次绑定，码发**目标新邮箱**；
      * ``new``  （需登录+有邮箱）：换绑第一步，码发**新邮箱**（独立验证）；
      * ``old``  （需登录+有邮箱）：换绑第二步，码发**旧邮箱**（账号主人确认）。
      换绑需 new + old 两码都通过（EmailChangeView）。
    防枚举：login purpose 对存在/不存在的邮箱返回一致文案。

    认证：沿用全局 JWTAuthentication（带 Bearer 可识别用户，匿名走 login 分支）。
    permission_classes 留空（login 公开）；其余分支手动校验登录态 +
    设备信任门（§9.3，与 IsAuthenticatedAndTrusted 等价）。
    """

    permission_classes: list = []

    def post(self, request):
        data = request.data or {}
        email = _valid_new_email(data.get("email"))
        purpose = (data.get("purpose") or "").strip()
        if purpose not in EmailCodeStore.PURPOSES:
            return Response(
                {"error": {"code": 400, "message": "purpose 参数无效"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if email is None:
            return Response(
                {"error": {"code": 400, "message": "邮箱格式不正确"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # 全局粗限流（IP 维度）
        if not check_rate_limit(request, *settings.RATE_LIMIT_GLOBAL_IP, scope="ip-coarse"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        user = getattr(request, "user", None)
        authed = (
            user is not None
            and getattr(user, "is_authenticated", False)
            and isinstance(user, PassportUser)
        )
        if purpose in ("bind", "new", "old") and (
            not authed or not _is_device_trusted(request)
        ):
            return Response(
                {"error": {"code": 401, "message": "该设备未受信任，请重新登录"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if purpose == "bind":
            # 首次绑定：当前无邮箱；码发目标新邮箱。
            if request.user.email:
                return Response(
                    {"error": {"code": 409, "message": "账户已绑定邮箱，请使用「更改邮箱」"}},
                    status=status.HTTP_409_CONFLICT,
                )
            if PassportUser.objects.filter(email__iexact=email).exists():
                return Response(
                    {"error": {"code": 409, "message": "该邮箱已被其他账户绑定"}},
                    status=status.HTTP_409_CONFLICT,
                )
            ok, err = _send_email_code(request, email, "bind")
        elif purpose == "new":
            # 换绑第一步：新邮箱独立验证，码发新邮箱。
            if not request.user.email:
                return Response(
                    {"error": {"code": 409, "message": "账户尚未绑定邮箱，请先绑定邮箱"}},
                    status=status.HTTP_409_CONFLICT,
                )
            if email == request.user.email.strip().lower():
                return Response(
                    {"error": {"code": 400, "message": "新邮箱不能与当前邮箱相同"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if PassportUser.objects.filter(email__iexact=email).exclude(pk=request.user.pk).exists():
                return Response(
                    {"error": {"code": 409, "message": "该邮箱已被其他账户绑定"}},
                    status=status.HTTP_409_CONFLICT,
                )
            ok, err = _send_email_code(request, email, "new")
        elif purpose == "old":
            # 换绑第二步：账号主人确认，码发旧邮箱。
            if not request.user.email:
                return Response(
                    {"error": {"code": 409, "message": "账户尚未绑定邮箱，请先绑定邮箱"}},
                    status=status.HTTP_409_CONFLICT,
                )
            ok, err = _send_email_code(request, request.user.email, "old")
        else:  # login：公开，码发给登录邮箱本身
            if not settings.PASSWORD_RESET_ENABLED:
                return Response(
                    {"error": {"code": 503, "message": "邮件服务未配置，暂时无法使用邮箱验证码登录"}},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            # 登录限流（按邮箱维度）
            if not check_rate_limit(
                request, *settings.RATE_LIMIT_LOGIN, scope="email-code", identifier=email
            ):
                return Response(
                    {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            ok, err = _send_email_code(request, email, "login")

        if not ok:
            # 503 类（SMTP 未配/故障）与 429（频率）分别透传语义
            status_code = status.HTTP_429_TOO_MANY_REQUESTS if "频繁" in err or "上限" in err else status.HTTP_503_SERVICE_UNAVAILABLE
            return Response({"error": {"code": status_code, "message": err}}, status=status_code)
        return Response({"detail": "验证码已发送，请查收邮件（含垃圾邮件箱）"}, status=status.HTTP_200_OK)


class EmailLoginView(APIView):
    """``POST /api/v1/login/email/  {email, code}`` — 验证码登录；无账号自动注册。

    与密码登录并行：已有账户直接登录；新邮箱自动建号（无密码、无 OAuth 绑定），
    后续可在账户安全页设置密码。建号即视为邮箱已验证（验证码本身就是所有权证明）。
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        data = request.data or {}
        email = _valid_new_email(data.get("email"))
        code = (data.get("code") or "").strip()
        if email is None:
            return Response(
                {"error": {"code": 400, "message": "邮箱格式不正确"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not code:
            return Response(
                {"error": {"code": 400, "message": "请输入邮件中的验证码"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not check_rate_limit(
            request, *settings.RATE_LIMIT_LOGIN, scope="email-login", identifier=email
        ):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not check_rate_limit(request, *settings.RATE_LIMIT_GLOBAL_IP, scope="ip-coarse"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not EmailCodeStore().verify(email, "login", code):
            record_login_failure(request=request, reason="bad_email_code")
            return Response(
                {"error": {"code": 401, "message": "验证码错误或已过期"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        user = PassportUser.objects.filter(email__iexact=email).first()
        created = False
        if user is None:
            # 自动注册：无密码（可用账户安全页设置），无 OAuth 绑定。
            user = PassportUser.objects.create_user(email=email)
            created = True
        if not user.is_active:
            return Response(
                {"error": {"code": 403, "message": "账户已被禁用"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        tokens = issue_tokens(user)
        record_login_success(user, jti=tokens["jti"], request=request)
        return Response(
            {**tokens, "created": created},
            status=status.HTTP_200_OK,
        )


class EmailBindView(APIView):
    """首次绑定邮箱（当前无邮箱账户）。

    ``POST /api/v1/security/email/bind/  {email, code, current_password?}``
    验证码已发到**目标新邮箱**；有密码账户须验密码（step-up）。
    """

    permission_classes = [IsAuthenticatedAndTrusted]

    def post(self, request):
        data = request.data or {}
        email = _valid_new_email(data.get("email"))
        code = (data.get("code") or "").strip()
        if email is None:
            return Response(
                {"error": {"code": 400, "message": "邮箱格式不正确"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if request.user.email:
            return Response(
                {"error": {"code": 409, "message": "账户已绑定邮箱，请使用「更改邮箱」"}},
                status=status.HTTP_409_CONFLICT,
            )
        # step-up：有密码账户须验密码（复用 verify_step_up）
        ok, err = verify_step_up(request.user, {"password": str(data.get("current_password") or "")})
        if not ok:
            return Response(
                {"error": {"code": 400, "message": err}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if PassportUser.objects.filter(email__iexact=email).exclude(pk=request.user.pk).exists():
            return Response(
                {"error": {"code": 409, "message": "该邮箱已被其他账户绑定"}},
                status=status.HTTP_409_CONFLICT,
            )
        if not EmailCodeStore().verify(email, "bind", code):
            return Response(
                {"error": {"code": 401, "message": "验证码错误或已过期"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            request.user.email = email
            request.user.save(update_fields=["email", "updated_at"])
        except IntegrityError:
            return Response(
                {"error": {"code": 409, "message": "该邮箱已被其他账户绑定"}},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {"detail": "邮箱绑定成功", "email": email},
            status=status.HTTP_200_OK,
        )


class EmailChangeView(APIView):
    """更改邮箱（已有邮箱账户）——双重验证。

    ``POST /api/v1/security/email/change/
        {new_email, new_code, old_code, current_password?}``

    * ``new_code``：发到**新邮箱**（purpose=new，证明拥有新邮箱）；
    * ``old_code``：发到**旧邮箱**（purpose=old，证明账号主人身份）；
    * 有密码账户另须验密码（step-up）。
    三者（两码 + 可能的密码）都通过才换绑。
    """

    permission_classes = [IsAuthenticatedAndTrusted]

    def post(self, request):
        data = request.data or {}
        new_email = _valid_new_email(data.get("new_email"))
        new_code = (data.get("new_code") or "").strip()
        old_code = (data.get("old_code") or "").strip()
        if new_email is None:
            return Response(
                {"error": {"code": 400, "message": "新邮箱格式不正确"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not request.user.email:
            return Response(
                {"error": {"code": 409, "message": "账户尚未绑定邮箱，请先绑定邮箱"}},
                status=status.HTTP_409_CONFLICT,
            )
        # step-up：有密码账户须验密码
        ok, err = verify_step_up(request.user, {"password": str(data.get("current_password") or "")})
        if not ok:
            return Response(
                {"error": {"code": 400, "message": err}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if new_email == request.user.email.strip().lower():
            return Response(
                {"error": {"code": 400, "message": "新邮箱不能与当前邮箱相同"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if PassportUser.objects.filter(email__iexact=new_email).exclude(pk=request.user.pk).exists():
            return Response(
                {"error": {"code": 409, "message": "该邮箱已被其他账户绑定"}},
                status=status.HTTP_409_CONFLICT,
            )
        store = EmailCodeStore()
        # 双重验证：新邮箱所有权 + 旧邮箱账号主人确认。
        if not store.verify(new_email, "new", new_code):
            return Response(
                {"error": {"code": 401, "message": "新邮箱验证码错误或已过期"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not store.verify(request.user.email, "old", old_code):
            return Response(
                {"error": {"code": 401, "message": "当前邮箱验证码错误或已过期"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            request.user.email = new_email
            request.user.save(update_fields=["email", "updated_at"])
        except IntegrityError:
            return Response(
                {"error": {"code": 409, "message": "该邮箱已被其他账户绑定"}},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {"detail": "邮箱已更改", "email": new_email},
            status=status.HTTP_200_OK,
        )


# --------------------------------------------------------------------------- #
# Passkeys / WebAuthn (§9.4b) — 已于 2026-08-27 正式移出范围
#
# 决策记录：注册端点自 2026-08-08 起因安全考量 501，登录端点也从未在前端
# 暴露。经用户确认整体砍除（模型/端点/前端 UI/依赖全删，迁移删表）。
# 历史设计见仓库 docs / HANDOVER.md §9.4b。
# --------------------------------------------------------------------------- #


def passport_configuration(request):
    """Machine-readable endpoint map so SDKs bootstrap from a single base URL.

    Deliberately NOT served at ``/.well-known/openid-configuration``: Lotus
    Passport is not a full OIDC provider (no ``id_token``, no ``/token`` grant
    endpoint), and squatting that path would make generic OIDC clients fail in
    confusing ways. SDKs read this document; humans read the README.
    """
    def abs_url(path: str) -> str:
        return request.build_absolute_uri(path)

    return JsonResponse(
        {
            "issuer": getattr(settings, "JWT_ISSUER", ""),
            "jwks_uri": abs_url("/.well-known/jwks.json"),
            "userinfo_endpoint": abs_url("/api/v1/userinfo/"),
            "token_refresh_endpoint": abs_url("/api/v1/token/refresh/"),
            "authorization_endpoint_template": abs_url(
                "/api/v1/oauth/{provider}/login/"
            ),
            "id_token_signing_alg_values_supported": [
                settings.SIMPLE_JWT.get("ALGORITHM", "RS256")
            ],
            "claims_supported": [
                "passport_user_id",
                "user_id",
                "email",
                "nickname",
                "exp",
                "iat",
                "jti",
                "iss",
            ],
            "providers_supported": sorted(
                p for p in REGISTRY if is_provider_configured(p)
            ),
        }
    )


def jwks_view(request):
    """Publish the RSA public key(s) for RS256 integrators (404 when RS256 off).

    Returns one JWK per retained key (the active key plus any still-valid
    previous keys during a rotation overlap), each tagged with its ``kid`` so
    offline integrators can verify tokens signed by any of them.
    """
    if settings.SIMPLE_JWT.get("ALGORITHM") != "RS256":
        return JsonResponse(
            {"error": "RS256 not enabled; configure an RSA keypair or set JWT_USE_RS256=True."},
            status=404,
        )
    import base64

    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    def _b64url_uint(value: int) -> str:
        length = max(1, (value.bit_length() + 7) // 8)
        return (
            base64.urlsafe_b64encode(value.to_bytes(length, "big"))
            .decode("ascii")
            .rstrip("=")
        )

    keys = []
    try:
        for kid, public_key in settings.KEY_STORE.all_public():
            key = load_pem_public_key(public_key.encode("utf-8"))
            numbers = key.public_numbers()
            keys.append(
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": kid,
                    "n": _b64url_uint(numbers.n),
                    "e": _b64url_uint(numbers.e),
                }
            )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": f"jwks unavailable: {exc}"}, status=500)
    if not keys:
        return JsonResponse({"error": "no public key configured"}, status=404)
    return JsonResponse({"keys": keys})


class OAuthGenericLoginView(APIView):
    """Provider-agnostic OAuth entry（GET /api/v1/oauth/login/）。

    接入方希望把整个登录体验交给护照时，从这里取一次性票据并跳转
    passport-web 登录页；用户以任意方式（本地邮箱/密码、第三方）登录后，
    web 调 POST /api/v1/oauth/continue/ 换取发往接入方的单次授权码。
    """

    authentication_classes: list = []  # public endpoint
    permission_classes: list = []

    def get(self, request):
        if not check_rate_limit(request, *settings.RATE_LIMIT_LOGIN, scope="oauth-login"):
            return Response(
                {"error": {"code": 429, "message": "请求过于频繁，请稍后再试"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        redirect_uri = request.GET.get("redirect_uri", "")
        # 通用入口发放的授权码会发往该地址：使用**独立精确白名单**
        # （OAUTH_GENERIC_ALLOWED_REDIRECT_URIS，逐条精确匹配）。origin 级
        # 匹配会为授权码注入留口子（接入方域内任意可控路径都可能接码）；
        # 未配置该白名单时通用入口整体拒绝（安全默认）。
        allowed = {
            u.strip().rstrip("/")
            for u in getattr(settings, "OAUTH_GENERIC_ALLOWED_REDIRECT_URIS", []) or []
        }
        # 测试/本地开发：localhost 与全局白名单行为保持一致
        from urllib.parse import urlparse as _urlparse

        from .redirects import _is_localhost

        parsed_cb = _urlparse(redirect_uri)
        if (
            redirect_uri
            and parsed_cb.scheme in ("http", "https")
            and (getattr(settings, "DEBUG", False) or getattr(settings, "TESTING", False))
            and _is_localhost(parsed_cb.hostname)
        ):
            allowed = allowed | {redirect_uri.rstrip("/")}
        if not redirect_uri or redirect_uri.rstrip("/") not in allowed:
            return Response(
                {
                    "error": {
                        "code": 400,
                        "message": (
                            "redirect_uri 不在允许列表中，请管理员在 "
                            "OAUTH_ALLOWED_REDIRECT_URIS 中配置精确回跳地址"
                        ),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        challenge, method = validate_code_challenge(
            request.GET.get("code_challenge"),
            request.GET.get("code_challenge_method"),
        )
        ticket = GenericLoginTicketStore().save(
            redirect_uri=redirect_uri,
            code_challenge=challenge or None,
            code_challenge_method=method or None,
        )
        # passport-web 登录页地址由授权确认页基地址推导（同 origin）
        web_origin = settings.OAUTH_CONSENT_PAGE_BASE.split("/oauth/")[0]
        return Response(
            {"login_url": f"{web_origin}/login?oticket={ticket}"}, status=200
        )


class OAuthContinueView(APIView):
    """用通用登录票据 + web 会话 JWT 换发往接入方的单次授权码。

    POST /api/v1/oauth/continue/ {ticket}，需携带 passport-web 登录后的
    ``Authorization: Bearer <access>``。响应为接入方 redirect_url（携带
    一次性 code；入口带 PKCE challenge 时 code 与之绑定）。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ticket = str((request.data or {}).get("ticket", ""))
        payload = GenericLoginTicketStore().consume(ticket) if ticket else None
        if not payload:
            return Response(
                {"error": {"code": 400, "message": "登录票据无效或已过期，请重新发起登录"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        redirect_uri = payload.get("redirect_uri", "")
        if not is_redirect_uri_allowed(redirect_uri):
            return Response(
                {"error": {"code": 400, "message": "redirect_uri 不在允许列表中"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tokens = issue_tokens(request.user, audience=_origin_of(redirect_uri))
        code = AuthCodeStore().save(
            access=tokens["access"],
            refresh=tokens["refresh"],
            token_type=tokens["token_type"],
            passport_user_id=tokens["passport_user_id"],
            code_challenge=payload.get("code_challenge"),
            code_challenge_method=payload.get("code_challenge_method"),
        )
        sep = "&" if "?" in redirect_uri else "?"
        return Response(
            {"redirect_url": f"{redirect_uri}{sep}code={code}"}, status=200
        )
