"""
用户视图 — 个人资料、第三方账号管理
"""
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import RetrieveUpdateAPIView

from .models import User
from .serializers import UserProfileSerializer, UserProfileUpdateSerializer


class UserProfileView(RetrieveUpdateAPIView):
    """获取/更新当前用户资料"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return UserProfileUpdateSerializer
        return UserProfileSerializer

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(request.user)
        return Response({'code': 200, 'message': 'ok', 'data': serializer.data})


class OAuthAccountsView(APIView):
    """查看/解绑第三方账号"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """查看已绑定的第三方账号"""
        accounts = request.user.oauth_accounts.all()
        data = [
            {
                'provider': a.provider,
                'provider_username': a.provider_username,
                'bound_at': a.bound_at,
            }
            for a in accounts
        ]
        return Response({'code': 200, 'message': 'ok', 'data': data})

    def delete(self, request, provider):
        """解绑指定第三方账号（至少保留一个）"""
        if provider not in ('wechat', 'qq', 'github'):
            return Response(
                {'code': 400, 'message': '不支持的第三方平台'},
                status=status.HTTP_400_BAD_REQUEST
            )

        account = request.user.oauth_accounts.filter(provider=provider).first()
        if not account:
            return Response(
                {'code': 404, 'message': '未绑定该第三方账号'},
                status=status.HTTP_404_NOT_FOUND
            )

        # 至少保留一个绑定
        if request.user.oauth_accounts.count() <= 1:
            return Response(
                {'code': 400, 'message': '至少保留一个第三方登录方式'},
                status=status.HTTP_400_BAD_REQUEST
            )

        account.delete()
        return Response({'code': 200, 'message': f'已解绑{provider}账号', 'data': None})