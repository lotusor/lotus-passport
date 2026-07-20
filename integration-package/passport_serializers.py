"""
通行证认证序列化器 — 用于 algo_rank 接入通行证
"""
from rest_framework import serializers


class PassportLoginSerializer(serializers.Serializer):
    """发起通行证OAuth登录"""
    provider = serializers.ChoiceField(
        choices=['wechat', 'qq', 'github'],
        error_messages={'invalid_choice': '不支持的登录方式'}
    )


class PassportCallbackSerializer(serializers.Serializer):
    """通行证OAuth回调"""
    provider = serializers.ChoiceField(choices=['wechat', 'qq', 'github'])
    code = serializers.CharField(min_length=1)
    state = serializers.CharField(min_length=1)


class PassportTokenLoginSerializer(serializers.Serializer):
    """通过通行证token直接登录"""
    passport_token = serializers.CharField(min_length=1, help_text="EACM通行证的access_token")
    school_id = serializers.IntegerField(required=False, write_only=True)