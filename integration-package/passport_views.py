"""
通行证认证视图 — algo_rank 接入 EACM 通行证的认证视图

管理员申请逻辑：
- 用户首次通过通行证登录时，可选择同时申请成为学校管理员
- apply_admin=True 时设置 is_admin=True, is_verified=False
- 后续由超管通过项目1自有的审核流程（QQ群验证）激活
"""
import logging
from django.conf import settings
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .passport_client import passport_client
from .passport_serializers import (
    PassportLoginSerializer, PassportCallbackSerializer,
    PassportTokenLoginSerializer,
)

logger = logging.getLogger(__name__)


def _build_user_response(user, is_new=False):
    """构建用户响应数据"""
    return {
        'access_token': str(RefreshToken.for_user(user).access_token),
        'refresh_token': str(RefreshToken.for_user(user)),
        'token_type': 'Bearer',
        'user': {
            'id': user.id,
            'username': user.username,
            'real_name': user.real_name,
            'phone': user.phone,
            'school': user.school.id if user.school else None,
            'school_name': user.school.name if user.school else None,
            'is_admin': user.is_admin,
            'is_verified': user.is_verified,
            'total_score': str(user.total_score),
            'contest_count': user.contest_count,
            'login_method': 'passport',
        },
        'is_new_user': is_new,
    }


def _create_local_user(passport_user_id, school, user_info, apply_admin=False, real_name='', phone=''):
    """创建本地用户"""
    from apps.auth_app.models import User

    nickname = user_info.get('nickname', f'passport_{passport_user_id}')
    username = nickname
    base_username = username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}_{counter}"
        counter += 1

    user = User(
        username=username,
        school=school,
        phone=phone,
        real_name=real_name if apply_admin else '',
        is_admin=apply_admin,
        is_verified=False,  # 管理员需要超管审核激活
        passport_user_id=passport_user_id,
        passport_nickname=user_info.get('nickname', ''),
        passport_avatar=user_info.get('avatar', ''),
    )
    user.set_unusable_password()
    user.save()
    return user


class PassportLoginView(APIView):
    """
    发起通行证OAuth登录
    POST /api/v1/auth/passport/login/<provider>/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not settings.EACM_PASSPORT_ENABLED:
            return Response(
                {'code': 503, 'message': '通行证登录未启用'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        serializer = PassportLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = serializer.validated_data['provider']

        result = passport_client.get_oauth_login_url(provider, settings.EACM_PASSPORT_CALLBACK_URL)
        if not result:
            return Response(
                {'code': 502, 'message': '通行证服务连接失败'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        return Response({'code': 0, 'message': 'success', 'data': result})


class PassportCallbackView(APIView):
    """
    通行证OAuth回调 — 新用户返回 need_bind_school
    POST /api/v1/auth/passport/callback/<provider>/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not settings.EACM_PASSPORT_ENABLED:
            return Response(
                {'code': 503, 'message': '通行证登录未启用'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        serializer = PassportCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = serializer.validated_data['provider']
        code = serializer.validated_data['code']
        state = serializer.validated_data['state']

        result = passport_client.handle_callback(provider, code, state, settings.EACM_PASSPORT_CALLBACK_URL)
        if not result:
            return Response(
                {'code': 502, 'message': '通行证认证失败'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        passport_user = result.get('user', {})
        passport_user_id = passport_user.get('id')
        is_new_user = result.get('is_new_user', False)
        passport_token = result.get('access_token', '')

        if not passport_user_id:
            return Response(
                {'code': 502, 'message': '通行证返回数据异常'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        from apps.auth_app.models import User
        user = User.objects.filter(passport_user_id=passport_user_id).first()

        if user:
            user.save(update_fields=['last_login'])
            return Response({'code': 0, 'message': '登录成功', 'data': _build_user_response(user)})

        # 新用户，需要选择学校
        return Response({
            'code': 10001,
            'message': '请选择所属学校以完成注册',
            'data': {
                'need_bind_school': True,
                'passport_user_id': passport_user_id,
                'passport_token': passport_token,
                'nickname': passport_user.get('nickname', ''),
                'avatar': passport_user.get('avatar', ''),
            }
        })


class PassportBindSchoolView(APIView):
    """
    通行证用户绑定学校并完成注册
    支持可选的管理员申请参数（apply_admin, real_name, phone）

    POST /api/v1/auth/passport/bind-school/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not settings.EACM_PASSPORT_ENABLED:
            return Response(
                {'code': 503, 'message': '通行证登录未启用'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        passport_user_id = request.data.get('passport_user_id')
        passport_token = request.data.get('passport_token')
        school_id = request.data.get('school_id')

        if not all([passport_user_id, passport_token, school_id]):
            return Response(
                {'code': 40001, 'message': '缺少必要参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 可选参数：管理员申请
        apply_admin = request.data.get('apply_admin', False)
        real_name = request.data.get('real_name', '')
        phone = request.data.get('phone', '')

        # 验证学校
        from apps.schools.models import School
        try:
            school = School.objects.get(id=school_id, is_active=True)
        except School.DoesNotExist:
            return Response(
                {'code': 40401, 'message': '该学校不存在或未启用'},
                status=status.HTTP_404_NOT_FOUND
            )

        # 验证通行证token
        user_info = passport_client.verify_token(passport_token)
        if not user_info or user_info.get('id') != passport_user_id:
            return Response(
                {'code': 40101, 'message': '通行证token验证失败'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        from apps.auth_app.models import User
        existing = User.objects.filter(passport_user_id=passport_user_id).first()
        if existing:
            return Response({'code': 0, 'message': '登录成功', 'data': _build_user_response(existing)})

        # 创建用户
        user = _create_local_user(passport_user_id, school, user_info, apply_admin, real_name, phone)
        return Response({'code': 0, 'message': '注册并登录成功', 'data': _build_user_response(user, is_new=True)})


class PassportTokenLoginView(APIView):
    """
    通过通行证token直接登录
    POST /api/v1/auth/passport/token-login/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not settings.EACM_PASSPORT_ENABLED:
            return Response(
                {'code': 503, 'message': '通行证登录未启用'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        serializer = PassportTokenLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        passport_token = serializer.validated_data['passport_token']
        school_id = serializer.validated_data.get('school_id')

        user_info = passport_client.verify_token(passport_token)
        if not user_info:
            return Response(
                {'code': 40101, 'message': '通行证token无效或已过期'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        passport_user_id = user_info['id']
        from apps.auth_app.models import User
        user = User.objects.filter(passport_user_id=passport_user_id).first()

        if user:
            return Response({'code': 0, 'message': '登录成功', 'data': _build_user_response(user)})

        if not school_id:
            return Response({
                'code': 10001,
                'message': '首次登录需选择所属学校',
                'data': {
                    'need_bind_school': True,
                    'passport_user_id': passport_user_id,
                    'nickname': user_info.get('nickname', ''),
                }
            })

        from apps.schools.models import School
        try:
            school = School.objects.get(id=school_id, is_active=True)
        except School.DoesNotExist:
            return Response(
                {'code': 40401, 'message': '该学校不存在或未启用'},
                status=status.HTTP_404_NOT_FOUND
            )

        user = _create_local_user(passport_user_id, school, user_info)
        return Response({'code': 0, 'message': '注册并登录成功', 'data': _build_user_response(user, is_new=True)})