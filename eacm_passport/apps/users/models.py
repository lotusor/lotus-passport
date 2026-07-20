"""
用户模型
"""
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    自定义用户模型
    - 通过OAuth第三方登录，不依赖密码和手机号
    - is_staff 仅为Django Admin后台权限标记，不代表业务管理员角色
    """

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"
        db_table = "eacm_user"

    id = models.BigAutoField(primary_key=True, verbose_name="用户ID")
    nickname = models.CharField(max_length=50, blank=True, default="", verbose_name="昵称")
    avatar = models.URLField(max_length=500, blank=True, default="", verbose_name="头像URL")
    is_staff = models.BooleanField(default=False, verbose_name="Django后台权限标记")
    is_active = models.BooleanField(default=True, verbose_name="是否激活")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    USERNAME_FIELD = 'id'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return f"{self.nickname or '未设置昵称'}({self.id})"

    @property
    def oauth_providers(self):
        """已绑定的第三方登录方式列表"""
        return list(
            self.oauth_accounts.values_list('provider', flat=True)
        )