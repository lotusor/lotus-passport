"""
OAuth认证视图 — 登录/回调/注销/令牌刷新
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import OAuthAccount
from .serializers import OAuthLoginSerializer, OAuthCallbackSerializer, TokenRefreshSerializer
from .providers.wechat import WeChatProvider
from .providers.qq import QQProvider
from .providers.github import GitHubProvider
from .providers.wechat import OAuthError

logger = logging.getLogger(__name__)

# 提供者注册表
PROVIDER_REGISTRY = {
    'wechat': WeChatProvider,
    'qq': QQProvider,
    'github': GitHubProvider,
}


def get_provider(provider_name):
    """获取OAuth提供者实例"""
    cls = PROVIDER_REGISTRY.get(provider_name)
    if not cls:
        return None
    config = settings.OAUTH_CONFIG.get(provider_name, {})
    return cls(config)


class OAuthLoginView(APIView):
    """
    发起第三方OAuth登录
    POST /api/auth/login/{provider}/
    返回授权跳转URL
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, provider):
        if provider not in PROVIDER_REGISTRY:
            return Response(
                {'code': 400, 'message': f'不支持的登录方式: {provider}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = OAuthLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        redirect_uri = serializer.validated_data['redirect_uri']

        p = get_provider(provider)
        if not p or not p.app_id:
            return Response(
                {'code': 503, 'message': f'{provider}登录服务暂未配置'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        state = p.generate_state()
        # 将state和redirect_uri存入缓存，用于回调验证
        cache.set(f'oauth_state_{state}', {
            'provider': provider,
            'redirect_uri': redirect_uri,
        }, timeout=settings.OAUTH_STATE_EXPIRES)

        authorize_url = p.build_authorize_url(redirect_uri, state)

        return Response({
            'code': 200,
            'message': 'ok',
            'data': {
                'authorization_url': authorize_url,
                'state': state,
            }
        })


class OAuthCallbackView(APIView):
    """
    OAuth回调处理
    POST /api/auth/callback/{provider}/
    前端拿到code后调用此接口完成登录
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, provider):
        if provider not in PROVIDER_REGISTRY:
            return Response(
                {'code': 400, 'message': f'不支持的登录方式: {provider}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = OAuthCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['code']
        state = serializer.validated_data['state']
        redirect_uri = serializer.validated_data['redirect_uri']

        # 验证state
        state_data = cache.get(f'oauth_state_{state}')
        if not state_data:
            return Response(
                {'code': 400, 'message': 'state无效或已过期，请重新登录'},
                status=status.HTTP_400_BAD_REQUEST
            )
        cache.delete(f'oauth_state_{state}')  # 一次性使用

        # 验证provider和redirect_uri匹配
        if state_data['provider'] != provider or state_data['redirect_uri'] != redirect_uri:
            return Response(
                {'code': 400, 'message': '回调参数不匹配'},
                status=status.HTTP_400_BAD_REQUEST
            )

        p = get_provider(provider)
        try:
            # 用code换取token
            token_response = p.exchange_token(code, redirect_uri)
            # 获取用户信息
            user_info = p.get_user_info(token_response)
        except OAuthError as e:
            logger.warning(f"OAuth {provider} 认证失败: {e}")
            return Response(
                {'code': 502, 'message': '第三方认证失败，请稍后重试'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            logger.error(f"OAuth {provider} 未知错误: {e}", exc_info=True)
            return Response(
                {'code': 500, 'message': '认证过程中发生错误'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        provider_user_id = user_info['provider_user_id']

        # 查找或创建用户
        is_new_user = False
        oauth_account = OAuthAccount.objects.filter(
            provider=provider, provider_user_id=provider_user_id
        ).select_related('user').first()

        if oauth_account:
            user = oauth_account.user
            # 更新token
            access_token = token_response.get('access_token', '')
            refresh_token = token_response.get('refresh_token', '')
            if access_token:
                oauth_account.set_access_token(access_token)
            if refresh_token:
                oauth_account.set_refresh_token(refresh_token)
            oauth_account.provider_username = user_info.get('nickname', '')
            # 计算过期时间
            expires_in = token_response.get('expires_in')
            if expires_in:
                oauth_account.token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
            oauth_account.save(
                update_fields=['access_token', 'refresh_token', 'provider_username', 'token_expires_at']
            )
        else:
            # 创建新用户
            from apps.users.models import User
            user = User.objects.create_user(
                nickname=user_info.get('nickname', ''),
                avatar=user_info.get('avatar', ''),
            )
            is_new_user = True

            # 创建OAuth绑定
            OAuthAccount.objects.create(
                user=user,
                provider=provider,
                provider_user_id=provider_user_id,
                provider_username=user_info.get('nickname', ''),
            )
            # 加密存储token
            access_token = token_response.get('access_token', '')
            refresh_token = token_response.get('refresh_token', '')
            if access_token:
                account = OAuthAccount.objects.get(user=user, provider=provider)
                account.set_access_token(access_token)
                if refresh_token:
                    account.set_refresh_token(refresh_token)
                expires_in = token_response.get('expires_in')
                if expires_in:
                    account.token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
                account.save(
                    update_fields=['access_token', 'refresh_token', 'token_expires_at']
                )

        # 签发JWT
        refresh = RefreshToken.for_user(user)
        return Response({
            'code': 200,
            'message': 'ok',
            'data': {
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'token_type': 'Bearer',
                'expires_in': settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds(),
                'user': {
                    'id': user.id,
                    'nickname': user.nickname,
                    'avatar': user.avatar,
                },
                'is_new_user': is_new_user,
            }
        })


class TokenRefreshView(APIView):
    """刷新JWT令牌"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token_str = serializer.validated_data['refresh_token']

        try:
            refresh = RefreshToken(refresh_token_str)
            data = {
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'token_type': 'Bearer',
                'expires_in': settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds(),
            }
            return Response({'code': 200, 'message': 'ok', 'data': data})
        except Exception as e:
            return Response(
                {'code': 401, 'message': '令牌无效或已过期'},
                status=status.HTTP_401_UNAUTHORIZED
            )


class LogoutView(APIView):
    """注销（将当前token加入黑名单）"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            token = RefreshToken(request.data.get('refresh_token'))
            token.blacklist()
        except Exception:
            pass
        return Response({'code': 200, 'message': '已注销', 'data': None})