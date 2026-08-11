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
import time
import io
import uuid
from urllib.parse import urlencode

from django.conf import settings
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
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied
from django.shortcuts import get_object_or_404
from django.db import IntegrityError

from .jwt import decode_access, issue_tokens
from .models import (
    AccountDeletion,
    OAuthAccount,
    Passkey,
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

from . import webauthn as wa
from .ratelimit import OAuthStateStore, AccountLockout, check_rate_limit
from .captcha import CaptchaVerifier
from .redirects import is_redirect_uri_allowed
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

    A user must keep at least one primary login method: a usable password, a
    Passkey, or another linked OAuth account. TOTP 2FA is NOT counted — it is
    step-up on top of a password and cannot log in by itself.
    """
    if user.has_usable_password():
        return True
    if getattr(user, "passkeys", None) and user.passkeys.exists():
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
        state = OAuthStateStore().save(provider, redirect_uri)
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
        tokens = issue_tokens(user)
        record_login_success(user, jti=tokens["jti"], request=request)

        # Use ONLY the redirect_uri stored in the validated OAuth state — never a
        # redirect_uri supplied directly on the callback (that would reopen the
        # open-redirect hole). Re-checked here as defence in depth.
        frontend = stored.get("redirect_uri") or ""
        if frontend and request.GET.get("response_mode") != "json":
            if not is_redirect_uri_allowed(frontend):
                return Response(
                    {"error": {"code": 400, "message": "redirect_uri 不在允许列表中"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            frag = urlencode(
                {
                    "access_token": tokens["access"],
                    "token_type": tokens["token_type"],
                    "refresh_token": tokens["refresh"],
                    "passport_user_id": tokens["passport_user_id"],
                }
            )
            from django.shortcuts import redirect

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


class OAuthBindView(APIView):
    """Initiate binding an OAuth provider to the CURRENT authenticated user (§9.2).

    Returns an ``authorize_url``; the browser completes the standard OAuth
    redirect and returns to the shared callback, which detects ``link_mode`` in
    the state and attaches the identity to this user instead of creating one.
    """

    permission_classes = [IsAuthenticated]

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

    Refuses to leave the account with no login method (password / Passkey /
    another OAuth account). TOTP alone does not count as a standalone method.
    """

    permission_classes = [IsAuthenticated]

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

    permission_classes = [IsAuthenticated]

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


class TokenRefreshView(_SimpleJWTRefresh):
    """Rotate an access token from a refresh token (simplejwt built-in)."""


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

    permission_classes = [IsAuthenticated]

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
    user.passkeys.all().delete()
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

    permission_classes = [IsAuthenticated]
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
            img = Image.open(upload).convert("RGBA")
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

    permission_classes = [IsAuthenticated]

    def get(self, request):
        devices = _owner_queryset(request, TrustedDevice)
        return Response(DeviceSerializer(devices, many=True).data)


class DeviceDetailView(APIView):
    """Rename / (un)trust / remove an authorized device (§9.3)."""

    permission_classes = [IsAuthenticated]

    def _get(self, request, pk: int) -> TrustedDevice:
        dev = get_object_or_404(_owner_queryset(request, TrustedDevice), pk=pk)
        return dev

    def patch(self, request, pk: int):
        dev = self._get(request, pk)
        ser = DeviceSerializer(dev, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        # 首次标记为信任时记录时间
        if ser.validated_data.get("trusted") and not dev.trusted:
            from django.utils import timezone

            dev.first_trusted_at = timezone.now()
        ser.save()
        return Response(DeviceSerializer(dev).data)

    def delete(self, request, pk: int):
        dev = self._get(request, pk)
        dev.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _current_jti(request) -> str | None:
    return _claims_of(request.auth).get("jti") if request.auth else None


class SessionListView(APIView):
    """List active sessions; DELETE revokes all *other* sessions (§9.4d)."""

    permission_classes = [IsAuthenticated]

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

    permission_classes = [IsAuthenticated]

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
    """Delete the session row and blacklist its jti (reuse logout path)."""
    try:
        RevocationStore().revoke(sess.jti, 60 * 60 * 24 * 14)
        sess.delete()
        return True
    except Exception:  # noqa: BLE001
        return False


class LoginHistoryView(APIView):
    """Recent login attempts for the user (§9.4e)."""

    permission_classes = [IsAuthenticated]

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

    permission_classes = [IsAuthenticated]

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

    permission_classes = [IsAuthenticated]

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
# Passkeys / WebAuthn (§9.4b)
# --------------------------------------------------------------------------- #
class PasskeyListView(APIView):
    """List the user's registered passkeys (security page)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = Passkey.objects.filter(user=request.user).order_by("-created_at")
        return Response({"passkeys": [pk.to_dict() for pk in items]})


class WebAuthnRegisterOptionsView(APIView):
    """Step 1 of registration: intentionally disabled (§9.4b 当前功能待开发)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response(
            {"error": {"code": 501, "message": "当前功能待开发"}},
            status=501,
        )


class WebAuthnRegisterView(APIView):
    """Step 2 of registration: intentionally disabled (§9.4b 当前功能待开发)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response(
            {"error": {"code": 501, "message": "当前功能待开发"}},
            status=501,
        )


class WebAuthnAuthOptionsView(APIView):
    """Step 1 of passwordless login: return assertion options + state token."""

    permission_classes = [AllowAny]

    def post(self, request):
        options_json, state = wa.build_authentication_options()
        return Response({"options": json.loads(options_json), "state": state})


class WebAuthnVerifyView(APIView):
    """Step 2 of passwordless login: verify assertion, issue JWT."""

    permission_classes = [AllowAny]

    def post(self, request):
        raw = request.data.get("response")
        state = request.data.get("state")
        if not raw or not state:
            return Response(
                {"error": {"code": 400, "message": "缺少 response 或 state"}},
                status=400,
            )
        try:
            user = wa.verify_authentication(raw, state)
        except wa.WebAuthnError as exc:
            return Response(
                {"error": {"code": exc.status_code, "message": str(exc)}},
                status=exc.status_code,
            )
        tokens = issue_tokens(user)
        record_login_success(user, jti=tokens["jti"], request=request)
        return Response(tokens)


class PasskeyDetailView(APIView):
    """Remove a passkey (owner only)."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        obj = Passkey.objects.filter(id=pk, user=request.user).first()
        if not obj:
            return Response(
                {"error": {"code": 404, "message": "通行密钥不存在"}}, status=404
            )
        obj.delete()
        return Response(status=204)


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
