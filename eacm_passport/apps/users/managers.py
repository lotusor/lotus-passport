"""
自定义用户管理器
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class UserManager(BaseUserManager):
    """自定义用户管理器 — 支持OAuth登录（无需密码）"""

    def create_user(self, **extra_fields):
        """创建普通用户（OAuth自动创建时调用）"""
        if not extra_fields.get('nickname'):
            extra_fields['nickname'] = f"用户{self.model.objects.count() + 1}"
        user = self.model(**extra_fields)
        user.set_unusable_password()  # OAuth用户不需要密码
        user.save(using=self._db)
        return user

    def create_superuser(self, password=None, **extra_fields):
        """创建超级管理员（命令行管理用）"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('超级管理员必须设置 is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('超级管理员必须设置 is_superuser=True.')

        user = self.model(**extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user