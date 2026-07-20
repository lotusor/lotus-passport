# 验证报告：EACM 通行证系统（v2 精简版）

**验证日期**: 2026-07-19
**验证范围**: v2 代码实际状态 — 通行证已精简为纯认证中心
**验证方法**: 逐项检查数据模型、API接口、认证流程、安全策略、前端页面与配置部署
**版本说明**: v2 将通行证定位为纯 OAuth 认证中心，手机号绑定、账户合并、管理员认证等功能已移除（职责归属接入方项目）

---

## 1. 数据模型验证

### 1.1 User（用户模型）

| 检查项 | 字段定义 | 实际实现 | 结果 |
|--------|----------|----------|------|
| 继承 | `AbstractBaseUser, PermissionsMixin` | `AbstractBaseUser, PermissionsMixin` | 一致 |
| `id` | `BigAutoField(primary_key=True)` | `BigAutoField(primary_key=True)` | 一致 |
| `nickname` | `CharField(max_length=50, blank=True, default="")` | `CharField(max_length=50, blank=True, default="")` | 一致 |
| `avatar` | `URLField(max_length=500, blank=True, default="")` | `URLField(max_length=500, blank=True, default="")` | 一致 |
| `is_staff` | `BooleanField(default=False)` | `BooleanField(default=False)` | 一致 |
| `is_active` | `BooleanField(default=True)` | `BooleanField(default=True)` | 一致 |
| `created_at` | `DateTimeField(auto_now_add=True)` | `DateTimeField(auto_now_add=True)` | 一致 |
| `updated_at` | `DateTimeField(auto_now=True)` | `DateTimeField(auto_now=True)` | 一致 |
| `USERNAME_FIELD` | `'id'` | `'id'` | 一致 |
| `REQUIRED_FIELDS` | `[]` | `[]` | 一致 |
| `objects` | `UserManager()` | `UserManager()` | 一致 |
| 额外属性 | — | 增加了 `oauth_providers` 属性 | **增强**（正向偏差） |

**结论**: User 模型字段精简为纯认证所需的最小集，符合纯认证中心的定位。`oauth_providers` 属性提供便捷的已绑定平台查询，属于合理增强。

### 1.2 OAuthAccount（第三方账号绑定）

| 检查项 | 字段定义 | 实际实现 | 结果 |
|--------|----------|----------|------|
| `id` | `BigAutoField(primary_key=True)` | `BigAutoField(primary_key=True)` | 一致 |
| `user` | `ForeignKey(User, CASCADE, related_name="oauth_accounts")` | `ForeignKey(AUTH_USER_MODEL, CASCADE, related_name="oauth_accounts")` | 一致 |
| `provider` | `CharField(max_length=20, choices)` | `CharField(max_length=20, choices=PROVIDER_CHOICES)` | 一致 |
| `provider_user_id` | `CharField(max_length=128)` | `CharField(max_length=128)` | 一致 |
| `provider_username` | `CharField(max_length=100, blank=True)` | `CharField(max_length=100, blank=True, default="")` | 一致 |
| `access_token` | `CharField(max_length=512, blank=True)` | `CharField(max_length=512, blank=True, default="")` | 一致 |
| `refresh_token` | `CharField(max_length=512, blank=True)` | `CharField(max_length=512, blank=True, default="")` | 一致 |
| `token_expires_at` | `DateTimeField(null=True, blank=True)` | `DateTimeField(null=True, blank=True)` | 一致 |
| `bound_at` | `DateTimeField(auto_now_add=True)` | `DateTimeField(auto_now_add=True)` | 一致 |
| `unique_together` | `('provider', 'provider_user_id')` | `('provider', 'provider_user_id')` | 一致 |
| AES加密存储 | 加密存储 | 实现了 `set_access_token`/`get_access_token` AES-256-CBC 加解密 | 一致 |

**结论**: OAuthAccount 模型完整保留，AES 加密存储实现正确。

### 1.3 AppClient（应用客户端）

| 检查项 | 状态 |
|--------|------|
| 模型实现 | **未实现** |

**标注**: 未来功能，当前未实现。用于外部应用接入管理，属于后续规划范围。

### 1.4 ER 关系验证

| 关系 | 实际实现 | 结果 |
|------|----------|------|
| User 1--* OAuthAccount | `related_name="oauth_accounts"` | 一致 |

**说明**: v2 精简后，ER 关系仅保留 User 与 OAuthAccount 的一对多关系。PhoneVerification 和 AdminCertification 模型已移除，相关关系不再存在。

---

## 2. API 接口验证

### 2.1 认证接口

| 接口 | 方法 | URL 路径 | 视图 | 序列化器 | 结果 |
|------|------|----------|------|----------|------|
| 发起 OAuth 登录 | POST | `/api/auth/login/{provider}/` | `OAuthLoginView` | `OAuthLoginSerializer` | 一致 |
| OAuth 回调 | POST | `/api/auth/callback/{provider}/` | `OAuthCallbackView` | `OAuthCallbackSerializer` | 一致 |
| 刷新令牌 | POST | `/api/auth/refresh/` | `TokenRefreshView` | `TokenRefreshSerializer` | 一致 |
| 注销 | POST | `/api/auth/logout/` | `LogoutView` | 无（直接读取 request.data） | 一致 |

**结论**: 认证接口完整保留，OAuth 回调返回的 user 对象仅包含 `id`、`nickname`、`avatar` 三个字段，符合纯认证中心定位。

### 2.2 用户接口

| 接口 | 方法 | URL 路径 | 视图 | 序列化器 | 结果 |
|------|------|----------|------|----------|------|
| 获取用户资料 | GET | `/api/user/profile/` | `UserProfileView` | `UserProfileSerializer` | 一致 |
| 更新用户资料 | PUT/PATCH | `/api/user/profile/` | `UserProfileView` | `UserProfileUpdateSerializer` (nickname, avatar) | 一致 |
| 查看第三方账号 | GET | `/api/user/oauth-accounts/` | `OAuthAccountsView` | 无（手动构造字典） | 一致 |
| 解绑第三方账号 | DELETE | `/api/user/oauth-accounts/{provider}/` | `OAuthAccountsView` | 无 | 一致 |

**已移除的接口**:
- `POST /api/user/verify-phone/` — 手机号绑定验证码（职责归属接入方项目）
- `POST /api/user/bind-phone/` — 手机号绑定（职责归属接入方项目）
- `POST /api/user/merge-accounts/` — 账户合并（职责归属接入方项目）
- `POST /api/admin/certify/` — 管理员认证申请（职责归属接入方项目）
- `GET /api/admin/certification-status/` — 认证状态查询（职责归属接入方项目）
- `GET /api/admin/pending-applications/` — 待审核列表（职责归属接入方项目）
- `POST /api/admin/review/{application_id}/` — 审核申请（职责归属接入方项目）

### 2.3 应用管理接口

| 接口 | 方法 | URL 路径 | 实现状态 |
|------|------|----------|----------|
| 注册新应用 | POST | `/api/apps/register/` | **未实现** |
| 获取应用列表 | GET | `/api/apps/` | **未实现** |
| 获取应用详情 | GET | `/api/apps/{client_id}/` | **未实现** |

**标注**: 未来功能，当前未实现。

---

## 3. 认证流程验证

### 3.1 OAuth 登录流程

| 步骤 | 要求 | 实际实现 | 结果 |
|------|------|----------|------|
| 1. 用户选择登录方式 | 微信/QQ/GitHub | `PROVIDER_REGISTRY` 注册了 wechat/qq/github | 一致 |
| 2. 前端跳转到 OAuth 授权页面 | POST login/{provider}/ 返回 authorization_url | `OAuthLoginView` 返回 `authorization_url` 和 `state` | 一致 |
| 3. 用户在第三方平台授权 | 由第三方处理 | 由第三方处理 | 不适用 |
| 4. 回调处理 | POST callback/{provider}/ 用 code 换 token | `OAuthCallbackView.exchange_token()` + `get_user_info()` | 一致 |
| 5. 查找或创建用户 | 已存在则找到 User 并签发 JWT；不存在则创建新 User + OAuthAccount | 完整实现查找/创建/更新 token 逻辑 | 一致 |
| 6. 签发 JWT | 返回 access_token, refresh_token, user, is_new_user | 完整返回所有字段，user 仅含 id/nickname/avatar | 一致 |

**State 防 CSRF**:
- 生成: `secrets.token_urlsafe(32)` — 使用密码学安全随机数，**合格**
- 存储: Django cache，超时 600 秒 — **合格**
- 验证: 回调时校验 provider + redirect_uri 匹配，一次性使用后删除 — **合格**

### 3.2 用户资料管理

| 功能 | URL | 说明 | 结果 |
|------|-----|------|------|
| 查看个人资料 | `GET /api/user/profile/` | 返回 id、nickname、avatar、is_staff、oauth_providers、created_at | 正常 |
| 更新昵称和头像 | `PUT /api/user/profile/` | 仅允许修改 nickname 和 avatar 字段 | 正常 |
| 查看第三方绑定 | `GET /api/user/oauth-accounts/` | 返回已绑定的第三方平台列表（provider、provider_username、bound_at） | 正常 |
| 解绑第三方账号 | `DELETE /api/user/oauth-accounts/{provider}/` | 至少保留一个绑定，防止用户无法登录 | 正常 |

**已移除的流程**:
- 手机号绑定流程（发送验证码 -> 验证绑定 -> 冲突检测 -> 账户合并）— 已移至接入方项目
- 管理员认证流程（申请 -> 审核 -> is_staff 标记）— 已移至接入方项目

---

## 4. 安全策略验证

### 4.1 JWT 安全

| 检查项 | 要求 | 实际实现 | 结果 |
|--------|------|----------|------|
| Access Token 有效期 | 2 小时 | 120 分钟（可通过环境变量配置） | 一致 |
| Refresh Token 有效期 | 30 天 | 2592000 秒 = 30 天（可通过环境变量配置） | 一致 |
| 签名算法 | RS256 非对称加密 | **使用 simplejwt 默认的 HS256** | **偏差** |
| Token 黑名单 | 注销时将 token 加入黑名单 | `BLACKLIST_AFTER_ROTATION: True`，`token_blacklist` 已注册到 `INSTALLED_APPS` | **已修复**（v1 的 S1 问题） |

**说明**: v2 已将 `rest_framework_simplejwt.token_blacklist` 加入 `INSTALLED_APPS`，v1 报告中的 S1 问题（Token 黑名单 App 未注册）已修复。注销功能（`token.blacklist()`）现在可以正常工作。

### 4.2 OAuth 安全

| 检查项 | 要求 | 实际实现 | 结果 |
|--------|------|----------|------|
| State 参数防 CSRF | 服务端生成并验证 | `secrets.token_urlsafe(32)` + cache 存储验证 | 一致 |
| 第三方 token 加密存储 | AES-256 | AES-256-CBC + PKCS7 填充 | 一致 |
| 回调 URL 白名单 | 严格校验 | 验证 state 中存储的 redirect_uri 与回调时传入的是否匹配 | 一致 |

### 4.3 通用安全

| 检查项 | 要求 | 实际实现 | 结果 |
|--------|------|----------|------|
| HTTPS | 所有 API 启用 HTTPS | 未在 settings 中强制 HTTPS（缺少 `SECURE_SSL_REDIRECT`） | **缺失** |
| 敏感字段不返回 | 密码/敏感字段不返回 | OAuthAccount 的 access_token/refresh_token 不会通过 API 返回；User 序列化器仅暴露 id/nickname/avatar/is_staff | 一致 |
| CORS 严格配置 | 严格配置 | 开发模式 `CORS_ALLOW_ALL_ORIGINS = DEBUG`，生产通过 `CORS_ALLOWED_ORIGINS` 环境变量 | **部分实现** |
| Rate Limiting | 限流 | `anon: 60/min`, `user: 120/min`, `sms: 10/hour` | 一致 |
| SQL 注入防护 | ORM 参数化查询 | 全部使用 Django ORM | 一致 |

### 4.4 安全策略汇总问题

1. **JWT 算法**（S2）: 若有安全要求需 RS256，当前使用 HS256。HS256 是对称加密，在分布式部署场景下安全性不如 RS256。若接受 HS256，应更新设计文档保持一致。
2. **HTTPS 强制**（M2）: 生产环境缺少 `SECURE_SSL_REDIRECT = True` 等安全配置。

---

## 5. 前端页面验证

### 5.1 现有 HTML 页面

| 文件 | 对应功能 |
|------|----------|
| `eacm-passport-design/pages/login.html` | 登录页面（第三方账号安全登录，无需绑定手机号） |
| `eacm-passport-design/pages/user-center.html` | 用户中心（个人资料、第三方账号管理） |

### 5.2 页面覆盖度检查

| 功能 | 对应页面 | 结果 |
|------|----------|------|
| OAuth 登录（微信/QQ/GitHub） | `login.html` | 存在 |
| 用户中心（个人资料、第三方账号绑定/解绑） | `user-center.html` | 存在 |

**已移除的页面**:
- `bind-phone.html` — 手机号绑定页面（已删除）
- `admin-certify.html` — 管理员认证申请页面（已删除）
- `admin-review.html` — 管理员审核面板页面（已删除）

**结论**: 前端页面精简为登录页和用户中心两个核心页面，覆盖了纯认证中心所需的全部场景。`login.html` 底部文案已更新为"第三方账号安全登录，无需绑定手机号"。`user-center.html` 已移除手机号和管理员认证相关 UI。

---

## 6. 配置与部署验证

### 6.1 Settings.py 完整性

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 自定义用户模型 | `AUTH_USER_MODEL = 'users.User'` | 正确 |
| JWT 配置 | `SIMPLE_JWT` 完整配置 | 正确 |
| CORS 配置 | 开发/生产双模式 | 正确 |
| OAuth 配置 | 三个平台配置齐全 | 正确 |
| AES 加密配置 | `AES_SECRET_KEY` | 正确 |
| 异常处理 | `EXCEPTION_HANDLER` 指向自定义处理器 | 正确 |
| `token_blacklist` 已注册 | `INSTALLED_APPS` 中包含 | 正确（v2 已修复） |
| `apps.admin_cert` 已移除 | `INSTALLED_APPS` 中不含 | 正确 |
| 缺少 `SECURE_SSL_REDIRECT` | 生产安全配置 | **问题** |
| 残留 `SMS_CONFIG` 和 `VERIFY_CODE` | settings.py 第 201-217 行 | **需清理**（v2 已移除短信服务，但配置块未同步删除） |

### 6.2 Requirements.txt 覆盖度

| 依赖 | 用途 | 状态 |
|------|------|------|
| `django>=5.0,<6.0` | 后端框架 | 正确 |
| `djangorestframework>=3.14` | REST API | 正确 |
| `djangorestframework-simplejwt>=5.3` | JWT 认证 | 正确 |
| `requests>=2.31` | HTTP 请求（OAuth） | 正确 |
| `authlib>=1.3` | OAuth 客户端库 | **已列出但未使用**（代码中使用 requests） |
| `django-cors-headers>=4.3` | CORS | 正确 |
| `django-filter>=23.5` | 过滤 | 正确 |
| `python-dotenv>=1.0` | 环境变量 | 正确 |
| `cryptography>=41.0` | AES 加密 | 正确 |
| `redis>=5.0` | 缓存 | 正确 |
| `gunicorn>=21.2` | WSGI 服务器 | 正确 |

### 6.3 项目结构对比

| 文件/目录 | 实际存在 | 结果 |
|-----------|----------|------|
| `manage.py` | 是 | 一致 |
| `requirements.txt` | 是 | 一致 |
| `eacm_passport/settings.py` | 是 | 一致 |
| `eacm_passport/urls.py` | 是 | 一致（仅含 api/auth/ 和 api/user/ 路由） |
| `apps/users/models.py` | 是 | 一致（仅含 User 模型） |
| `apps/users/serializers.py` | 是 | 一致（仅含 UserProfileSerializer 和 UserProfileUpdateSerializer） |
| `apps/users/views.py` | 是 | 一致（仅含 UserProfileView 和 OAuthAccountsView） |
| `apps/users/urls.py` | 是 | 一致（仅含 profile/ 和 oauth-accounts/） |
| `apps/users/managers.py` | 是 | 存在（残留 phone 相关代码，见问题 A4） |
| `apps/oauth/models.py` | 是 | 一致 |
| `apps/oauth/views.py` | 是 | 一致 |
| `apps/oauth/providers/` (wechat/qq/github) | 是 | 一致 |
| `apps/admin_cert/` | **否** | 已移除（v2 正确） |
| 前端页面 | `eacm-passport-design/pages/` | 仅含 login.html 和 user-center.html |
| 集成包 | `integration-package/` | 含 passport_client.py、passport_views.py、passport_serializers.py、apply_integration.py |

### 6.4 根 URL 路由

| 路由 | 状态 |
|------|------|
| `api/auth/` | 存在（OAuth 认证） |
| `api/user/` | 存在（用户资料） |
| `api/admin/` | **已移除**（v2 正确） |

---

## 7. 发现的问题与建议

### [严重] 会导致系统功能异常或安全漏洞的问题

**S1. Token 黑名单 App 未注册 — 已修复**
- **状态**: v2 已在 `INSTALLED_APPS` 中添加 `'rest_framework_simplejwt.token_blacklist'`。注销功能（`LogoutView` 中 `token.blacklist()`）现在可以正常工作。

**S2. JWT 签名算法与设计文档不符**
- **位置**: `eacm_passport/settings.py` -> `SIMPLE_JWT`
- **问题**: 设计文档要求 RS256 非对称加密，但 `SIMPLE_JWT` 中配置了 `ALGORITHM: 'HS256'`。HS256 是对称加密，在分布式部署场景下安全性不如 RS256。
- **修复**: 如需 RS256，需生成 RSA 密钥对并配置 `ALGORITHM = 'RS256'`、`PUBLIC_KEY`、`PRIVATE_KEY`。若接受 HS256，应更新设计文档保持一致。

### [中等] 影响安全性或需要关注的问题

**M2. 缺少生产环境 HTTPS 安全配置**
- **位置**: `eacm_passport/settings.py`
- **问题**: 生产环境未配置 `SECURE_SSL_REDIRECT`、`SESSION_COOKIE_SECURE`、`CSRF_COOKIE_SECURE` 等安全选项。
- **修复**: 根据 `DEBUG` 变量条件性添加安全配置：`SECURE_SSL_REDIRECT = not DEBUG`、`SESSION_COOKIE_SECURE = not DEBUG`、`CSRF_COOKIE_SECURE = not DEBUG`。

**M3. .env.example 缺少 CORS_ALLOWED_ORIGINS 配置项**
- **位置**: `.env.example`
- **问题**: `settings.py` 在非 DEBUG 模式下读取 `CORS_ALLOWED_ORIGINS` 环境变量，但 `.env.example` 中未列出此项，部署时容易遗漏。
- **修复**: 在 `.env.example` 中添加 `CORS_ALLOWED_ORIGINS=https://yourdomain.com`。

**M4. AppClient 模型及应用管理接口完全缺失**
- **位置**: 整个 `apps/` 目录
- **问题**: 应用管理接口完全未实现，包括 AppClient 模型、序列化器、视图和 URL 路由。
- **修复**: 作为未来功能实现，或在设计文档中标注为二期功能。

**M6. settings.py 残留短信服务配置块**
- **位置**: `eacm_passport/settings.py` 第 201-217 行
- **问题**: `SMS_CONFIG` 和 `VERIFY_CODE` 配置块在 v2 中已无任何代码引用（PhoneVerification 模型已删除、SendPhoneCodeView 已移除），但仍保留在 settings.py 中。
- **修复**: 删除 `SMS_CONFIG` 和 `VERIFY_CODE` 配置块，保持配置文件整洁。

**M7. DRF 限流配置残留 sms 类**
- **位置**: `eacm_passport/settings.py` -> `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES`
- **问题**: 仍配置了 `'sms': '10/hour'` 限流规则，但已无任何视图使用该限流类。
- **修复**: 从 `DEFAULT_THROTTLE_RATES` 中移除 `'sms'` 条目。

### [建议] 改进与最佳实践建议

**A1. authlib 依赖未使用**
- **问题**: `requirements.txt` 中列出了 `authlib>=1.3`，但代码库中没有任何模块导入使用 authlib。OAuth 流程完全使用 `requests` 库实现。
- **建议**: 移除 `authlib` 依赖，减少安装体积。

**A2. OAuthError 定义位置不合理**
- **位置**: `apps/oauth/providers/wechat.py`
- **问题**: `OAuthError` 异常类定义在 `wechat.py` 中，但 `qq.py`、`github.py` 和 `views.py` 都需要导入它。从 `wechat.py` 导入通用异常类违反模块职责单一原则。
- **建议**: 将 `OAuthError` 移至 `providers/base.py` 或单独的 `providers/exceptions.py` 中。

**A3. UserManager 残留 phone 相关代码**
- **位置**: `apps/users/managers.py`
- **问题**: `create_superuser()` 仍以 `phone` 作为必选参数，并引用 `phone_verified` 字段；`get_by_phone()` 方法查询已不存在的 `phone` 字段。User 模型已移除 `phone` 和 `phone_verified` 字段，调用 `createsuperuser` 命令会出错。
- **修复**: 重写 `create_superuser()` 使其不依赖 phone 字段（仅需 is_staff/is_superuser 参数），删除 `get_by_phone()` 方法。

**A4. 新用户创建时未加密存储 OAuth Token（优化建议）**
- **位置**: `apps/oauth/views.py` -> `OAuthCallbackView.post()`
- **问题**: 创建新用户时先 `OAuthAccount.objects.create()` 再调用 `set_access_token()` 加密存储，产生两次数据库写入。
- **建议**: 在 create 前准备好加密后的 token 字段值，一次 save 完成。

**A5. 建议增加 DRF 的 DEFAULT_RENDERER_CLASSES 配置**
- **问题**: 未显式配置 JSON 渲染器，浏览器直接访问 API 时会返回 Browsable API。
- **建议**: 在 `REST_FRAMEWORK` 中添加 `DEFAULT_RENDERER_CLASSES` 配置，生产环境禁用 Browsable API。

---

## 8. 总结

### 完成度评估

| 模块 | 完成度 | 说明 |
|------|--------|------|
| 用户模型 (User) | 100% | 精简为 id/nickname/avatar/is_staff/is_active/created_at/updated_at |
| OAuth 模型 (OAuthAccount) | 100% | 完全实现，含 AES 加密 |
| 手机号验证模型 (PhoneVerification) | — | 已移除（职责归属接入方项目） |
| 管理员认证模型 (AdminCertification) | — | 已移除（职责归属接入方项目） |
| 应用客户端模型 (AppClient) | 0% | 未来功能，当前未实现 |
| 认证 API (login/callback/refresh/logout) | 100% | 完全实现，callback 返回精简 user 对象 |
| 用户 API (profile/oauth-accounts) | 100% | 完全实现 |
| 手机号绑定/账户合并 API | — | 已移除（职责归属接入方项目） |
| 管理员认证 API | — | 已移除（职责归属接入方项目） |
| 应用管理 API (apps) | 0% | 未来功能，当前未实现 |
| OAuth 提供者 (WeChat/QQ/GitHub) | 100% | 三个平台全部实现 |
| 安全策略 | 90% | S1 已修复；剩余 S2（JWT 算法）、M2（HTTPS 配置） |
| 前端页面 | 100% | login.html + user-center.html 覆盖全部场景 |
| 配置与部署 | 85% | 基本完整，存在残留配置待清理 |
| 集成包 | 100% | passport_client/serializers/views 齐全，支持 apply_admin 参数 |

### 整体评价

v2 将 EACM 通行证精简为纯 OAuth 认证中心，定位清晰。系统仅保留核心的第三方登录认证和用户基本资料管理，手机号绑定、账户合并、管理员认证等功能已正确移除，职责划分合理。

**主要优势**:
1. 代码精简后职责单一，各模块边界清晰，维护成本降低。
2. v1 的 S1 问题（token_blacklist 未注册）已修复，注销功能可正常工作。
3. 集成包设计合理，passport_client/passport_views/passport_serializers 三个文件即可完成接入方集成，`apply_integration.py` 一键脚本降低了接入门槛。
4. OAuth 回调返回的 user 对象仅含 id/nickname/avatar，最小化信息暴露。

**需关注事项**:
1. JWT 算法使用 HS256 而非设计文档要求的 RS256（**S2**），需根据实际安全需求决定是否升级。
2. 生产环境缺少 HTTPS 强制配置（**M2**），部署前需补全。
3. `managers.py` 中 `create_superuser` 仍依赖已删除的 `phone` 字段（**A3**），运行 `manage.py createsuperuser` 会报错，需尽快修复。
4. `settings.py` 中 `SMS_CONFIG` 和 `VERIFY_CODE` 配置块为残留代码（**M6**），建议清理。