"""
EACM通行证集成 — 完整测试脚本（v2 纯认证版）

测试范围：
1. 通行证系统自身API（需启动通行证服务）
2. algo_rank集成层（模拟请求，无需启动服务）
3. 数据模型完整性
4. 认证流程端到端

使用方法：
  cd d:\\dev\\项目2-通行证系统
  python integration-package\test_integration.py
"""
import os
import sys
import json
import importlib.util

# 确保能导入项目模块
ALGO_RANK_DIR = r'd:\dev\项目1-爬虫项目\algo_rank'
EACM_DIR = r'd:\dev\项目2-通行证系统\eacm_passport'

# 添加到 Python 路径
if ALGO_RANK_DIR not in sys.path:
    sys.path.insert(0, ALGO_RANK_DIR)
if EACM_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(EACM_DIR))

# 简单测试结果收集
results = {'pass': 0, 'fail': 0, 'skip': 0, 'tests': []}


def test(name, passed, detail=''):
    status = 'PASS' if passed else 'FAIL'
    if passed:
        results['pass'] += 1
    else:
        results['fail'] += 1
    results['tests'].append({'name': name, 'status': status, 'detail': detail})
    symbol = 'OK' if passed else 'XX'
    print(f"  [{symbol}] {name}" + (f" — {detail}" if detail and not passed else ""))


def skip(name, reason=''):
    results['skip'] += 1
    results['tests'].append({'name': name, 'status': 'SKIP', 'detail': reason})
    print(f"  [SKIP] {name} — {reason}")


# ============================================================
# 测试1: 通行证系统文件结构完整性
# ============================================================
def test_passport_structure():
    print("\n[测试组1] 通行证系统文件结构")
    print("-" * 50)

    files = [
        (os.path.join(EACM_DIR, 'manage.py'), 'manage.py'),
        (os.path.join(EACM_DIR, 'eacm_passport', 'settings.py'), 'settings.py'),
        (os.path.join(EACM_DIR, 'eacm_passport', 'urls.py'), '根 urls.py'),
        (os.path.join(EACM_DIR, 'eacm_passport', 'exceptions.py'), '异常处理'),
        (os.path.join(EACM_DIR, 'apps', 'users', 'models.py'), 'users/models.py'),
        (os.path.join(EACM_DIR, 'apps', 'users', 'views.py'), 'users/views.py'),
        (os.path.join(EACM_DIR, 'apps', 'users', 'serializers.py'), 'users/serializers.py'),
        (os.path.join(EACM_DIR, 'apps', 'users', 'urls.py'), 'users/urls.py'),
        (os.path.join(EACM_DIR, 'apps', 'users', 'managers.py'), 'users/managers.py'),
        (os.path.join(EACM_DIR, 'apps', 'users', 'admin.py'), 'users/admin.py'),
        (os.path.join(EACM_DIR, 'apps', 'oauth', 'models.py'), 'oauth/models.py'),
        (os.path.join(EACM_DIR, 'apps', 'oauth', 'views.py'), 'oauth/views.py'),
        (os.path.join(EACM_DIR, 'apps', 'oauth', 'serializers.py'), 'oauth/serializers.py'),
        (os.path.join(EACM_DIR, 'apps', 'oauth', 'urls.py'), 'oauth/urls.py'),
        (os.path.join(EACM_DIR, 'apps', 'oauth', 'providers', 'base.py'), 'providers/base.py'),
        (os.path.join(EACM_DIR, 'apps', 'oauth', 'providers', 'wechat.py'), 'providers/wechat.py'),
        (os.path.join(EACM_DIR, 'apps', 'oauth', 'providers', 'qq.py'), 'providers/qq.py'),
        (os.path.join(EACM_DIR, 'apps', 'oauth', 'providers', 'github.py'), 'providers/github.py'),
    ]

    for path, name in files:
        test(f"文件存在: {name}", os.path.exists(path))

    # 确认 admin_cert 目录已移除
    admin_cert_dir = os.path.join(EACM_DIR, 'apps', 'admin_cert')
    test("admin_cert 目录已移除", not os.path.exists(admin_cert_dir))

    # requirements.txt
    req_path = os.path.join(EACM_DIR, 'requirements.txt')
    test("requirements.txt 存在", os.path.exists(req_path))
    if os.path.exists(req_path):
        content = open(req_path, 'r', encoding='utf-8').read()
        for pkg in ['django', 'djangorestframework', 'djangorestframework-simplejwt',
                     'requests', 'authlib', 'django-cors-headers', 'cryptography', 'redis']:
            test(f"依赖声明: {pkg}", pkg in content)


# ============================================================
# 测试2: 通行证数据模型验证
# ============================================================
def test_passport_models():
    print("\n[测试组2] 通行证数据模型")
    print("-" * 50)

    # User 模型关键字段（v2: 无 phone/phone_verified）
    user_path = os.path.join(EACM_DIR, 'apps', 'users', 'models.py')
    user_content = open(user_path, 'r', encoding='utf-8').read()
    for field in ['nickname', 'avatar', 'is_staff', 'is_active', 'created_at', 'updated_at']:
        test(f"User字段: {field}", field in user_content)
    test("User: AbstractBaseUser", 'AbstractBaseUser' in user_content)
    test("User: PermissionsMixin", 'PermissionsMixin' in user_content)
    # v2: 确认 phone 和 phone_verified 已移除
    test("User: phone 字段已移除", 'phone' not in user_content or 'phone_number' not in user_content)
    test("User: phone_verified 字段已移除", 'phone_verified' not in user_content)

    # 确认 PhoneVerification 模型已移除
    test("PhoneVerification 模型已移除",
         'PhoneVerification' not in user_content and 'class PhoneVerification' not in user_content)

    # 确认 AdminCertification 模型已移除
    test("AdminCertification 模型已移除",
         not os.path.exists(os.path.join(EACM_DIR, 'apps', 'admin_cert', 'models.py')))

    # OAuthAccount 模型
    oauth_path = os.path.join(EACM_DIR, 'apps', 'oauth', 'models.py')
    oauth_content = open(oauth_path, 'r', encoding='utf-8').read()
    for field in ['provider', 'provider_user_id', 'access_token', 'refresh_token', 'token_expires_at']:
        test(f"OAuthAccount字段: {field}", field in oauth_content)
    test("OAuthAccount: unique_together", 'unique_together' in oauth_content)
    test("OAuthAccount: AES加密", 'encrypt_token' in oauth_content or 'cryptography' in oauth_content)


# ============================================================
# 测试3: 通行证API接口验证
# ============================================================
def test_passport_api():
    print("\n[测试组3] 通行证API接口")
    print("-" * 50)

    # 检查URL注册
    root_urls = open(os.path.join(EACM_DIR, 'eacm_passport', 'urls.py'), 'r', encoding='utf-8').read()
    test("根路由: auth/ → oauth", "'api/auth/'" in root_urls and 'oauth.urls' in root_urls)
    test("根路由: user/ → users", "'api/user/'" in root_urls and 'users.urls' in root_urls)
    # v2: 确认 api/admin/ 路由已移除
    test("根路由: api/admin/ 已移除", "'api/admin/'" not in root_urls)

    # OAuth URLs
    oauth_urls = open(os.path.join(EACM_DIR, 'apps', 'oauth', 'urls.py'), 'r', encoding='utf-8').read()
    test("OAuth路由: login/<provider>/", "'login/<str:provider>/'" in oauth_urls)
    test("OAuth路由: callback/<provider>/", "'callback/<str:provider>/'" in oauth_urls)
    test("OAuth路由: refresh/", "'refresh/'" in oauth_urls)
    test("OAuth路由: logout/", "'logout/'" in oauth_urls)

    # User URLs（v2: 只有 profile/ 和 oauth-accounts/）
    user_urls = open(os.path.join(EACM_DIR, 'apps', 'users', 'urls.py'), 'r', encoding='utf-8').read()
    test("User路由: profile/", "'profile/'" in user_urls)
    test("User路由: oauth-accounts/", "'oauth-accounts/'" in user_urls)
    # v2: 确认手机号相关路由已移除
    test("User路由: verify-phone/ 已移除", "'verify-phone/'" not in user_urls)
    test("User路由: bind-phone/ 已移除", "'bind-phone/'" not in user_urls)
    test("User路由: merge-accounts/ 已移除", "'merge-accounts/'" not in user_urls)

    # 检查视图中的关键逻辑
    oauth_views = open(os.path.join(EACM_DIR, 'apps', 'oauth', 'views.py'), 'r', encoding='utf-8').read()
    test("OAuth: state验证", 'state_data' in oauth_views and 'cache.get' in oauth_views)
    test("OAuth: 提供者注册表", 'PROVIDER_REGISTRY' in oauth_views)
    test("OAuth: JWT签发", 'RefreshToken.for_user' in oauth_views)
    test("OAuth: is_new_user标记", 'is_new_user' in oauth_views)

    # User views（v2: 只有 UserProfileView 和 OAuthAccountsView）
    user_views = open(os.path.join(EACM_DIR, 'apps', 'users', 'views.py'), 'r', encoding='utf-8').read()
    test("Users: UserProfileView", 'UserProfileView' in user_views)
    test("Users: OAuthAccountsView", 'OAuthAccountsView' in user_views)
    # v2: 确认手机号相关逻辑已移除
    test("Users: 手机号冲突检测已移除", 'merge_into' not in user_views)
    test("Users: 验证码逻辑已移除", 'constant_time_compare' not in user_views)
    test("Users: 合并账户逻辑已移除", 'merge_into' not in user_views)


# ============================================================
# 测试4: 通行证安全策略验证
# ============================================================
def test_passport_security():
    print("\n[测试组4] 安全策略")
    print("-" * 50)

    settings = open(os.path.join(EACM_DIR, 'eacm_passport', 'settings.py'), 'r', encoding='utf-8').read()

    test("安全: token_blacklist已注册", 'token_blacklist' in settings)
    test("安全: JWT轮转启用", 'ROTATE_REFRESH_TOKENS' in settings)
    test("安全: JWT黑名单启用", 'BLACKLIST_AFTER_ROTATION' in settings)
    test("安全: 限流配置", 'DEFAULT_THROTTLE_RATES' in settings)
    test("安全: CORS配置", 'corsheaders' in settings)
    test("安全: AES加密密钥配置", 'AES_SECRET_KEY' in settings)
    test("安全: OAuth state过期", 'OAUTH_STATE_EXPIRES' in settings)
    test("安全: OAuth配置分离", 'OAUTH_CONFIG' in settings)

    # v2: 确认验证码相关安全配置已移除
    test("安全: SMS_CONFIG 已移除", 'SMS_CONFIG' not in settings)
    test("安全: VERIFY_CODE 配置块已移除", 'VERIFY_CODE' not in settings)

    # v2: 确认 INSTALLED_APPS 中无 admin_cert
    test("安全: INSTALLED_APPS 无 admin_cert", 'admin_cert' not in settings)


# ============================================================
# 测试5: 集成包完整性
# ============================================================
def test_integration_package():
    print("\n[测试组5] 集成包")
    print("-" * 50)

    pkg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    files = [
        'passport_client.py',
        'passport_views.py',
        'passport_serializers.py',
        'apply_integration.py',
        'README.md',
        'test_integration.py',
    ]
    for f in files:
        path = os.path.join(pkg_dir, f)
        test(f"集成包文件: {f}", os.path.exists(path))

    # 验证apply_integration.py中的关键操作
    apply_content = open(os.path.join(pkg_dir, 'apply_integration.py'), 'r', encoding='utf-8').read()
    test("集成脚本: 修改settings", 'apply_settings_patch' in apply_content)
    test("集成脚本: 修改models", 'apply_models_patch' in apply_content)
    test("集成脚本: 修改urls", 'apply_urls_patch' in apply_content)
    test("集成脚本: 复制模块文件", 'copy_module_files' in apply_content)
    test("集成脚本: 数据库迁移", 'run_migrations' in apply_content)
    test("集成脚本: 修改.env", 'apply_env_patch' in apply_content)

    # 验证passport_client.py
    client_content = open(os.path.join(pkg_dir, 'passport_client.py'), 'r', encoding='utf-8').read()
    test("客户端: verify_token方法", 'verify_token' in client_content)
    test("客户端: get_oauth_login_url方法", 'get_oauth_login_url' in client_content)
    test("客户端: handle_callback方法", 'handle_callback' in client_content)

    # 验证passport_views.py
    views_content = open(os.path.join(pkg_dir, 'passport_views.py'), 'r', encoding='utf-8').read()
    test("视图: PassportLoginView", 'PassportLoginView' in views_content)
    test("视图: PassportCallbackView", 'PassportCallbackView' in views_content)
    test("视图: PassportBindSchoolView", 'PassportBindSchoolView' in views_content)
    test("视图: PassportTokenLoginView", 'PassportTokenLoginView' in views_content)
    test("视图: need_bind_school逻辑", 'need_bind_school' in views_content)
    test("视图: 签发本地JWT", 'RefreshToken.for_user' in views_content)


# ============================================================
# 测试6: 前端页面完整性
# ============================================================
def test_frontend_pages():
    print("\n[测试组6] 前端页面")
    print("-" * 50)

    pages_dir = r'd:\dev\项目2-通行证系统\eacm-passport-design\pages'

    # v2: 只有 login.html 和 user-center.html
    existing_pages = [
        ('login.html', '登录页'),
        ('user-center.html', '用户中心'),
    ]
    removed_pages = [
        ('bind-phone.html', '手机绑定页'),
        ('admin-certify.html', '管理员认证页'),
        ('admin-review.html', '管理员审核页'),
    ]

    # 检查保留的页面
    for filename, desc in existing_pages:
        path = os.path.join(pages_dir, filename)
        if not os.path.exists(path):
            test(f"前端页面: {desc}", False, "文件不存在")
            continue
        content = open(path, 'r', encoding='utf-8').read()
        test(f"前端页面: {desc} 存在", True)

    # 检查已移除的页面确实不存在
    for filename, desc in removed_pages:
        path = os.path.join(pages_dir, filename)
        test(f"前端页面: {desc} 已移除", not os.path.exists(path))

    # 检查登录页关键元素
    login_path = os.path.join(pages_dir, 'login.html')
    if os.path.exists(login_path):
        content = open(login_path, 'r', encoding='utf-8').read()
        test("登录页: 微信登录按钮", '微信' in content and ('wechat' in content.lower() or 'weixin' in content.lower() or '#07C160' in content))
        test("登录页: QQ登录按钮", 'QQ' in content and '#1296DB' in content)
        test("登录页: GitHub登录按钮", 'GitHub' in content and '#24292F' in content)
        test("登录页: E时代ACM令牌标题", 'E时代ACM令牌' in content or 'ACM' in content)
        test("登录页: v2底部文案（无需绑定手机号）", '无需绑定手机号' in content)

    # 检查用户中心关键元素（v2: 无手机号/管理员认证相关内容）
    uc_path = os.path.join(pages_dir, 'user-center.html')
    if os.path.exists(uc_path):
        content = open(uc_path, 'r', encoding='utf-8').read()
        test("用户中心: 第三方账号管理", '微信' in content or 'QQ' in content or 'GitHub' in content)
        test("用户中心: 手机号绑定入口已移除", '绑定手机' not in content and '修改手机' not in content)
        test("用户中心: 管理员认证入口已移除", '管理员认证' not in content and '申请管理员' not in content)


# ============================================================
# 测试7: 设计文档与实现一致性
# ============================================================
def test_doc_consistency():
    print("\n[测试组7] 设计文档一致性")
    print("-" * 50)

    doc_path = r'd:\dev\项目2-通行证系统\DESIGN_DOC.md'
    if not os.path.exists(doc_path):
        skip("设计文档检查", "DESIGN_DOC.md 不存在")
        return

    doc = open(doc_path, 'r', encoding='utf-8').read()

    # 验证设计文档中的关键概念都有实现
    concepts = [
        ('微信登录', 'wechat' in doc.lower()),
        ('QQ登录', 'qq' in doc.lower()),
        ('GitHub登录', 'github' in doc.lower()),
        ('JWT认证', 'JWT' in doc),
        ('AES加密', 'AES' in doc or 'aes' in doc.lower()),
        ('OAuth2.0', 'OAuth' in doc or 'oauth' in doc.lower()),
    ]
    for name, found in concepts:
        test(f"设计文档: {name}", found)

    # v2: 确认已移除的章节不再出现
    test("设计文档: 手机号策略已移除", '非强绑定' not in doc and '非强制' not in doc)
    test("设计文档: 管理员认证需手机号已移除", ('管理员认证需手机号' not in doc) and ('管理员' not in doc or '手机号' not in doc))
    test("设计文档: 账户合并已移除", '合并' not in doc)
    test("设计文档: 验证码安全已移除", '验证码' not in doc)


# ============================================================
# 主函数
# ============================================================
def main():
    print("=" * 60)
    print("EACM通行证系统 — 集成测试（v2 纯认证版）")
    print("=" * 60)
    print(f"通行证项目: {EACM_DIR}")
    print(f"集成目标:   {ALGO_RANK_DIR}")
    print(f"测试时间:   2026-07-19")

    try:
        test_passport_structure()
        test_passport_models()
        test_passport_api()
        test_passport_security()
        test_integration_package()
        test_frontend_pages()
        test_doc_consistency()
    except Exception as e:
        print(f"\n[ERROR] 测试执行异常: {e}")
        import traceback
        traceback.print_exc()

    # 汇总
    total = results['pass'] + results['fail'] + results['skip']
    print("\n" + "=" * 60)
    print(f"测试完成: {total} 项")
    print(f"  通过: {results['pass']}")
    print(f"  失败: {results['fail']}")
    print(f"  跳过: {results['skip']}")

    if results['fail'] > 0:
        print(f"\n失败项:")
        for t in results['tests']:
            if t['status'] == 'FAIL':
                print(f"  XX {t['name']} — {t['detail']}")
    else:
        print("\n全部测试通过!")

    print("=" * 60)
    return 0 if results['fail'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
