"""
OAuth认证序列化器
"""
import os
from rest_framework import serializers


class OAuthLoginSerializer(serializers.Serializer):
    """发起OAuth登录"""
    redirect_uri = serializers.URLField(
        allow_blank=False,
        error_messages={'invalid': '请提供有效的回调地址'}
    )

    def validate_redirect_uri(self, value):
        """校验 redirect_uri 是否在白名单中"""
        allowed = os.getenv('OAUTH_ALLOWED_REDIRECT_URIS', '').split(',')
        # 开发模式下放行 localhost
        if not allowed and value.startswith('http://localhost'):
            return value
        if allowed and value not in allowed:
            raise serializers.ValidationError('不合法的回调地址')
        return value


class OAuthCallbackSerializer(serializers.Serializer):
    """OAuth回调处理"""
    code = serializers.CharField(
        min_length=1,
        error_messages={'blank': '缺少授权码code'}
    )
    state = serializers.CharField(
        min_length=1,
        error_messages={'blank': '缺少state参数'}
    )
    redirect_uri = serializers.URLField()


class TokenRefreshSerializer(serializers.Serializer):
    """刷新JWT令牌"""
    refresh_token = serializers.CharField()