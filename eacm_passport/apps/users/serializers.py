"""
用户序列化器
"""
from rest_framework import serializers
from .models import User


class UserProfileSerializer(serializers.ModelSerializer):
    """用户资料序列化器"""
    oauth_providers = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )

    class Meta:
        model = User
        fields = (
            'id', 'nickname', 'avatar', 'is_staff',
            'oauth_providers', 'created_at'
        )
        read_only_fields = ('id', 'is_staff', 'oauth_providers', 'created_at')


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """用户资料更新序列化器"""

    class Meta:
        model = User
        fields = ('nickname', 'avatar')
        extra_kwargs = {
            'nickname': {'max_length': 50, 'allow_blank': True},
            'avatar': {'max_length': 500, 'allow_blank': True},
        }