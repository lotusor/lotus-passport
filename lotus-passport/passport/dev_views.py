"""
Development-only endpoints.

These exist so the SPA can exercise the full login → JWT → userinfo loop
without registering real WeChat / QQ / GitHub OAuth applications.

The routes are always mounted in ``passport/urls.py``, but every view here
hard-fails with 404 at request time unless ``settings.ENABLE_DEV_LOGIN`` is
True (defaults to DEBUG). That gate — not the route's mere existence — is what
keeps a stub login from being reachable in production, because a production
build with DEBUG=False makes ``ENABLE_DEV_LOGIN`` default to False.
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .jwt import issue_tokens
from .providers import Identity
from .ratelimit import AuthCodeStore, validate_code_challenge
from .redirects import is_redirect_uri_allowed, _origin_of
from .views import link_or_create_user
from .auth_events import record_login_success

# Deterministic fake accounts, one per provider, so repeated dev logins land on
# the same PassportUser instead of piling up junk rows.
_DEV_IDENTITIES: dict[str, dict[str, str]] = {
    "github": {
        "provider_user_id": "dev-github-1001",
        "email": "dev.github@lotus.local",
        "nickname": "GitHub 开发者",
        "avatar": "https://avatars.githubusercontent.com/u/9919?s=200&v=4",
    },
    "wechat": {
        "provider_user_id": "dev-wechat-1001",
        "email": "dev.wechat@lotus.local",
        "nickname": "微信开发者",
        "avatar": "",
    },
    "qq": {
        "provider_user_id": "dev-qq-1001",
        "email": "dev.qq@lotus.local",
        "nickname": "QQ 开发者",
        "avatar": "",
    },
}


def _guard() -> None:
    """Raise 404 unless dev stub login is explicitly enabled."""
    if not settings.ENABLE_DEV_LOGIN:
        raise Http404("dev endpoints are disabled")


class DevLoginView(APIView):
    """Issue a real JWT for a fake identity — DEBUG only.

    Query params:
        provider:     github | wechat | qq   (default: github)
        redirect_uri: if present, 302 back with tokens in the URL fragment,
                      mirroring the real callback flow the SPA already handles.
        code_challenge / code_challenge_method:
                      PKCE（RFC 7636）。提供时走「授权码 + PKCE」模式——
                      只回跳一次性 code，令牌由前端 POST /api/v1/oauth/token/
                      换取（与真实登录的新模式完全一致）。
    """

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        _guard()
        provider = (request.GET.get("provider") or "github").lower()
        spec = _DEV_IDENTITIES.get(provider)
        if spec is None:
            return Response(
                {"error": {"code": 400, "message": f"不支持的 OAuth 提供商: {provider}"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pair = validate_code_challenge(
            request.GET.get("code_challenge"),
            request.GET.get("code_challenge_method"),
        )
        if pair is None:
            return Response(
                {
                    "error": {
                        "code": 400,
                        "message": "code_challenge / code_challenge_method 参数无效",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        challenge, challenge_method = pair

        identity = Identity(
            provider_user_id=spec["provider_user_id"],
            email=spec["email"],
            nickname=spec["nickname"],
            avatar=spec["avatar"],
        )
        # Reuse the production link/create path so dev users go through exactly
        # the same persistence + token-encryption code as real ones.
        user = link_or_create_user(
            identity,
            provider,
            {"access_token": "dev-access-token", "refresh_token": "dev-refresh-token"},
            timezone.now() + timedelta(hours=2),
        )
        redirect_uri = request.GET.get("redirect_uri")
        tokens = issue_tokens(user, audience=(_origin_of(redirect_uri) if redirect_uri else None))
        record_login_success(user, jti=tokens["jti"], request=request)

        if redirect_uri:
            # Same allow-list as the real flow — dev logins must not bypass the
            # open-redirect protection. localhost is auto-allowed under DEBUG/TESTING.
            if not is_redirect_uri_allowed(redirect_uri):
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
            if challenge:
                code = AuthCodeStore().save(
                    access=tokens["access"],
                    refresh=tokens["refresh"],
                    token_type=tokens["token_type"],
                    passport_user_id=tokens["passport_user_id"],
                    code_challenge=challenge,
                    code_challenge_method=challenge_method,
                )
                return redirect(f"{redirect_uri}?code={code}")
            frag = urlencode(
                {
                    "access_token": tokens["access"],
                    "token_type": tokens["token_type"],
                    "refresh_token": tokens["refresh"],
                    "passport_user_id": tokens["passport_user_id"],
                }
            )
            return redirect(f"{redirect_uri}#{frag}")
        return Response(tokens, status=status.HTTP_200_OK)


def dev_status(request):
    """Tiny probe so the SPA can decide whether to show the 'dev login' button.

    Always reachable (it only reports config — no secrets, no auth bypass), so
    the frontend can detect dev mode without guessing.
    """
    enabled = bool(settings.ENABLE_DEV_LOGIN)
    return JsonResponse(
        {
            "debug": bool(settings.DEBUG),
            "dev_login_enabled": enabled,
            "providers": sorted(_DEV_IDENTITIES) if enabled else [],
        }
    )
