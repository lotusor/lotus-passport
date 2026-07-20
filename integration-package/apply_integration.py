"""
一键应用 EACM 通行证集成到 algo_rank 项目

使用方法：
  cd d:\\dev\\项目1-爬虫项目
  python d:\\dev\\项目2-通行证系统\\integration-package\\apply_integration.py

脚本会自动：
1. 修改 config/settings.py — 添加通行证配置
2. 修改 apps/auth_app/models.py — 添加 passport_user_id 字段
3. 修改 apps/auth_app/urls.py — 添加通行证路由
4. 复制通行证模块文件
5. 修改 .env — 添加通行证环境变量
6. 修改 requirements.txt — 添加依赖
7. 生成并应用数据库迁移
"""
import os
import sys
import shutil

# algo_rank 项目根目录
ALGO_RANK_DIR = r'd:\dev\项目1-爬虫项目\algo_rank'
# 本集成包目录
INTEGRATION_DIR = os.path.dirname(os.path.abspath(__file__))
# 上级目录（.env 和 requirements.txt 所在）
PROJECT_ROOT = os.path.dirname(ALGO_RANK_DIR)


def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  [OK] 写入: {path}")


def apply_settings_patch():
    """修改 settings.py 添加通行证配置"""
    path = os.path.join(ALGO_RANK_DIR, 'config', 'settings.py')
    content = read_file(path)

    if 'EACM_PASSPORT' in content:
        print("  [SKIP] settings.py 已包含通行证配置")
        return

    patch = '''

# ============================================================
# EACM 通行证集成配置
# ============================================================
EACM_PASSPORT_ENABLED = os.getenv('EACM_PASSPORT_ENABLED', 'True').lower() in ('true', '1', 'yes')
EACM_PASSPORT_BASE_URL = os.getenv('EACM_PASSPORT_BASE_URL', 'http://localhost:8001').rstrip('/')
EACM_PASSPORT_CLIENT_ID = os.getenv('EACM_PASSPORT_CLIENT_ID', '')
EACM_PASSPORT_CLIENT_SECRET = os.getenv('EACM_PASSPORT_CLIENT_SECRET', '')
EACM_PASSPORT_CALLBACK_URL = os.getenv('EACM_PASSPORT_CALLBACK_URL', '')
EACM_PASSPORT_TOKEN_VERIFY_TIMEOUT = 10

# Token 黑名单支持（注销功能）
if 'rest_framework_simplejwt.token_blacklist' not in INSTALLED_APPS:
    INSTALLED_APPS.insert(
        INSTALLED_APPS.index('rest_framework_simplejwt') + 1,
        'rest_framework_simplejwt.token_blacklist',
    )
'''

    content = content.rstrip() + patch
    write_file(path, content)


def apply_models_patch():
    """修改 User 模型添加通行证字段"""
    path = os.path.join(ALGO_RANK_DIR, 'apps', 'auth_app', 'models.py')
    content = read_file(path)

    if 'passport_user_id' in content:
        print("  [SKIP] models.py 已包含通行证字段")
        return

    # 在 last_login 字段后添加通行证字段
    patch = '''
    # EACM 通行证关联字段
    passport_user_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name='通行证用户ID')
    passport_nickname = models.CharField(max_length=50, blank=True, default='', verbose_name='通行证昵称')
    passport_avatar = models.URLField(max_length=500, blank=True, default='', verbose_name='通行证头像')
    login_method = models.CharField(max_length=20, blank=True, default='local', verbose_name='登录方式')
'''

    # 在 last_login 行后插入
    lines = content.split('\n')
    new_lines = []
    inserted = False
    for line in lines:
        new_lines.append(line)
        if "last_login" in line and not inserted and "models.DateTimeField" in line:
            new_lines.append(patch.strip())
            inserted = True

    write_file(path, '\n'.join(new_lines))


def apply_urls_patch():
    """修改 auth_app/urls.py 添加通行证路由"""
    path = os.path.join(ALGO_RANK_DIR, 'apps', 'auth_app', 'urls.py')
    content = read_file(path)

    if 'passport' in content:
        print("  [SKIP] urls.py 已包含通行证路由")
        return

    patch = '''
    # EACM 通行证登录路由
    path('passport/login/', include('apps.auth_app.passport_urls')),
'''

    content = content.rstrip()
    if content.endswith("]"):
        # 在urlpatterns列表最后一项后插入
        lines = content.split('\n')
        new_lines = []
        for i, line in enumerate(lines):
            new_lines.append(line)
            if "name='verify-admin'" in line:
                new_lines.append(patch.strip())
        content = '\n'.join(new_lines)

    write_file(path, content)


def create_passport_urls():
    """创建 passport_urls.py 路由文件"""
    path = os.path.join(ALGO_RANK_DIR, 'apps', 'auth_app', 'passport_urls.py')
    if os.path.exists(path):
        print(f"  [SKIP] {path} 已存在")
        return

    content = '''"""EACM通行证认证路由"""
from django.urls import path
from .passport_views import (
    PassportLoginView,
    PassportCallbackView,
    PassportBindSchoolView,
    PassportTokenLoginView,
)

urlpatterns = [
    path('<str:provider>/', PassportLoginView.as_view(), name='passport-login'),
    path('callback/', PassportCallbackView.as_view(), name='passport-callback'),
    path('callback/<str:provider>/', PassportCallbackView.as_view(), name='passport-callback-provider'),
    path('bind-school/', PassportBindSchoolView.as_view(), name='passport-bind-school'),
    path('token-login/', PassportTokenLoginView.as_view(), name='passport-token-login'),
]
'''
    write_file(path, content)


def copy_module_files():
    """复制通行证模块文件到 algo_rank"""
    files = [
        ('passport_client.py', 'apps/auth_app/passport_client.py'),
        ('passport_views.py', 'apps/auth_app/passport_views.py'),
        ('passport_serializers.py', 'apps/auth_app/passport_serializers.py'),
    ]

    for src_name, dest_rel in files:
        src = os.path.join(INTEGRATION_DIR, src_name)
        dest = os.path.join(ALGO_RANK_DIR, dest_rel)
        if os.path.exists(dest):
            print(f"  [SKIP] {dest_rel} 已存在")
        else:
            shutil.copy2(src, dest)
            print(f"  [OK] 复制: {dest_rel}")


def apply_env_patch():
    """修改 .env 添加通行证环境变量"""
    path = os.path.join(PROJECT_ROOT, '.env')
    if not os.path.exists(path):
        print("  [WARN] .env 文件不存在，跳过")
        return

    content = read_file(path)
    if 'EACM_PASSPORT' in content:
        print("  [SKIP] .env 已包含通行证配置")
        return

    patch = '''

# EACM 通行证配置
EACM_PASSPORT_ENABLED=True
EACM_PASSPORT_BASE_URL=http://localhost:8001
EACM_PASSPORT_CLIENT_ID=algo_rank
EACM_PASSPORT_CLIENT_SECRET=algo_rank_secret_change_in_production
EACM_PASSPORT_CALLBACK_URL=http://localhost:8000/api/v1/auth/passport/callback/
'''
    content += patch
    write_file(path, content)


def apply_requirements_patch():
    """修改 requirements.txt 添加依赖"""
    path = os.path.join(PROJECT_ROOT, 'requirements.txt')
    content = read_file(path)

    if 'cryptography' in content:
        print("  [SKIP] requirements.txt 已包含 cryptography")
        return

    patch = '\n# EACM Passport integration\ncryptography>=41.0\n'
    content += patch
    write_file(path, content)


def run_migrations():
    """生成并应用数据库迁移"""
    import subprocess

    print("\n[3/3] 生成数据库迁移...")
    os.chdir(ALGO_RANK_DIR)

    # makemigrations
    result = subprocess.run(
        [sys.executable, 'manage.py', 'makemigrations', 'auth_app'],
        capture_output=True
    )
    stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
    stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
    if result.returncode == 0:
        print(f"  [OK] makemigrations: {stdout.strip()}")
    else:
        print(f"  [WARN] makemigrations: {(stderr or stdout).strip()}")

    # migrate
    result = subprocess.run(
        [sys.executable, 'manage.py', 'migrate'],
        capture_output=True
    )
    stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
    stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
    if result.returncode == 0:
        print(f"  [OK] migrate: 迁移已应用")
    else:
        print(f"  [WARN] migrate: {(stderr or stdout).strip()}")


def main():
    print("=" * 60)
    print("EACM通行证集成 — 应用到 algo_rank 项目")
    print("=" * 60)
    print(f"目标项目: {ALGO_RANK_DIR}")
    print(f"集成包:   {INTEGRATION_DIR}")
    print()

    print("[1/3] 修改现有文件...")
    apply_settings_patch()
    apply_models_patch()
    apply_urls_patch()
    apply_env_patch()
    apply_requirements_patch()

    print("\n[2/3] 创建新文件...")
    copy_module_files()
    create_passport_urls()

    print()
    run_migrations()

    print()
    print("=" * 60)
    print("集成完成!")
    print()
    print("新增API接口:")
    print("  POST /api/v1/auth/passport/login/<provider>/   发起OAuth登录")
    print("  POST /api/v1/auth/passport/callback/           OAuth回调")
    print("  POST /api/v1/auth/passport/bind-school/        绑定学校")
    print("  POST /api/v1/auth/passport/token-login/        Token直接登录")
    print()
    print("前端集成流程:")
    print("  1. 用户点击'微信/QQ/GitHub登录' → 调用 login/ 获取授权URL")
    print("  2. 跳转到通行证授权页 → 用户授权 → 通行证回调")
    print("  3. 前端拿到code → 调用 callback/ → 获取algo_rank的JWT")
    print("  4. 若返回 need_bind_school=true → 前端展示学校选择 → 调用 bind-school/")
    print("=" * 60)


if __name__ == '__main__':
    main()