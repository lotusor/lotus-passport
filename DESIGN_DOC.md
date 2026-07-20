# E时代ACM令牌 — 通行证系统设计文档

## 1. 系统概述

**系统名称**: E时代ACM令牌 (EACM Passport)  
**定位**: 独立统一认证通行证，服务于未来所有项目的用户登录注册  
**核心策略**: 第三方OAuth登录 + JWT认证，纯认证中心定位

---

## 2. 认证策略

### 2.1 登录方式

| 登录方式 | 说明 |
|---------|------|
| 微信 (WeChat) | OAuth2.0 授权码模式，通过微信开放平台 |
| QQ | OAuth2.0 授权码模式，通过QQ互联 |
| GitHub | OAuth2.0 授权码模式，通过GitHub OAuth App |

### 2.2 通行证定位

EACM 通行证是一个**纯认证中心**，职责仅包括：

- 提供第三方 OAuth 登录（微信 / QQ / GitHub）
- 签发和管理 JWT 令牌
- 维护用户基本身份信息（昵称、头像）
- 管理第三方账号绑定关系

通行证**不包含**业务权限管理。管理员角色、业务审批等逻辑由各接入方项目自行实现。例如，项目 `algo_rank`（算法排名系统）的管理员申请是在其集成层通过 `PassportBindSchoolView` 的 `apply_admin` 参数实现，通行证仅负责验证用户身份并返回 JWT，不参与业务权限判断。

接入方项目通过 JWT 中携带的用户 `id` 与通行证进行关联，在各自业务库中维护独立的权限和角色体系。

---

## 3. 数据模型设计

### 3.1 User（用户模型）

```python
class User(AbstractBaseUser, PermissionsMixin):
    """
    自定义用户模型 — 替代Django默认auth_user
    """
    id = BigAutoField(primary_key=True)
    nickname = models.CharField(max_length=50, blank=True, default="", verbose_name="昵称")
    avatar = models.URLField(max_length=500, blank=True, default="", verbose_name="头像URL")
    is_staff = models.BooleanField(default=False, verbose_name="管理员")
    is_active = models.BooleanField(default=True, verbose_name="是否激活")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'id'  # 使用ID作为登录字段（实际通过OAuth）
    REQUIRED_FIELDS = []

    objects = UserManager()
```

> `is_staff` 字段保留用于 Django 管理后台权限控制，不作为业务管理员标识。业务侧管理员角色由接入方项目自行管理。

### 3.2 OAuthAccount（第三方账号绑定）

```python
class OAuthAccount(models.Model):
    """
    第三方OAuth账号绑定记录
    一个用户可绑定多个第三方账号（微信/QQ/GitHub）
    """
    id = BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="oauth_accounts")
    provider = models.CharField(max_length=20, choices=Provider.choices)  # wechat/qq/github
    provider_user_id = models.CharField(max_length=128)  # 第三方平台用户ID
    provider_username = models.CharField(max_length=100, blank=True)  # 第三方平台用户名
    access_token = models.CharField(max_length=512, blank=True)  # 加密存储
    refresh_token = models.CharField(max_length=512, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    bound_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('provider', 'provider_user_id')
```

### 3.3 AppClient（应用客户端）

```python
class AppClient(models.Model):
    """
    接入通行证的外部应用客户端
    """
    id = BigAutoField(primary_key=True)
    name = models.CharField(max_length=100)
    client_id = models.CharField(max_length=64, unique=True)
    client_secret = models.CharField(max_length=128)
    redirect_uris = models.JSONField(default=list)  # 允许的回调地址列表
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### 3.4 ER关系图

```
User 1──* OAuthAccount        (一个用户多个第三方绑定)
AppClient (独立)              (接入应用管理)
```

---

## 4. API接口设计

### 4.1 认证相关接口

#### POST `/api/auth/login/{provider}/`
发起第三方OAuth登录，获取授权跳转URL

**请求体**:
```json
{
  "redirect_uri": "https://myapp.com/callback"
}
```

**响应**:
```json
{
  "authorization_url": "https://open.weixin.qq.com/connect/oauth2/authorize?...",
  "state": "random_state_string"
}
```

#### POST `/api/auth/callback/{provider}/`
第三方OAuth回调处理

**请求体**:
```json
{
  "code": "oauth_authorization_code",
  "state": "random_state_string",
  "redirect_uri": "https://myapp.com/callback"
}
```

**响应**:
```json
{
  "access_token": "jwt_access_token",
  "refresh_token": "jwt_refresh_token",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user": {
    "id": 1,
    "nickname": "用户昵称",
    "avatar": "https://..."
  },
  "is_new_user": true
}
```

#### POST `/api/auth/refresh/`
刷新JWT令牌

**请求体**:
```json
{ "refresh_token": "jwt_refresh_token" }
```

#### POST `/api/auth/logout/`
注销（使当前令牌失效）

---

### 4.2 用户相关接口

#### GET `/api/user/profile/`
获取当前用户信息

#### PUT `/api/user/profile/`
更新用户资料（昵称、头像）

#### GET `/api/user/oauth-accounts/`
查看已绑定的第三方账号列表

#### DELETE `/api/user/oauth-accounts/{provider}/`
解绑指定第三方账号（至少保留一个绑定）

---

### 4.3 应用管理接口（内部管理）

#### POST `/api/apps/register/`
注册新的接入应用

#### GET `/api/apps/`
获取已注册应用列表

#### GET `/api/apps/{client_id}/`
获取应用详情

---

## 5. 认证流程详解

### 5.1 首次登录流程

```
用户选择微信/QQ/GitHub登录
        │
        ▼
前端跳转到OAuth授权页面
        │
        ▼
用户在第三方平台授权
        │
        ▼
第三方回调 → POST /api/auth/callback/{provider}/
        │
        ▼
后端用code换取access_token → 获取第三方用户信息
        │
        ▼
查询OAuthAccount表
    ├── 已存在 → 找到关联User → 签发JWT → 返回
    └── 不存在 → 创建新User + OAuthAccount → 签发JWT → 返回is_new_user=true
```

---

## 6. 安全策略

### 6.1 JWT安全
- Access Token 有效期: 2小时
- Refresh Token 有效期: 30天
- Token使用RS256非对称加密
- Refresh Token支持单设备限制（可配置）

### 6.2 OAuth安全
- State参数防CSRF，服务端生成并验证
- 第三方access_token加密存储（AES-256）
- 回调URL严格白名单校验

### 6.3 通用安全
- 所有API启用HTTPS
- 密码/敏感字段不返回前端
- CORS严格配置
- Rate Limiting（限流）
- SQL注入防护（ORM参数化查询）

---

## 7. 技术栈

| 层级 | 技术选型 |
|------|---------|
| 后端框架 | Django 5.x + Django REST Framework |
| 认证 | JWT (djangorestframework-simplejwt) |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| OAuth客户端 | requests-oauthlib / Authlib |
| 缓存 | Redis（限流） |
| 前端 | HTML + Tailwind CSS（设计稿阶段） |
| 部署 | Docker + Nginx + Gunicorn |

---

## 8. 项目结构

```
eacm_passport/
├── manage.py
├── requirements.txt
├── eacm_passport/           # 项目配置
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── __init__.py
│   ├── users/              # 用户管理
│   │   ├── __init__.py
│   │   ├── models.py       # User
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── managers.py     # UserManager
│   ├── oauth/              # OAuth认证
│   │   ├── __init__.py
│   │   ├── models.py       # OAuthAccount
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── providers/      # 各平台适配器
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── wechat.py
│   │   │   ├── qq.py
│   │   │   └── github.py
│   │   └── admin.py
├── templates/              # 前端模板（设计稿）
│   ├── login.html
│   ├── register.html
│   └── user_center.html
└── static/                 # 静态资源
    ├── css/
    └── images/
```

---

## 9. 第三方OAuth配置参数

| 平台 | 需要配置的参数 | 申请地址 |
|------|-------------|---------|
| 微信 | AppID, AppSecret | https://open.weixin.qq.com |
| QQ | AppID, AppKey | https://connect.qq.com |
| GitHub | Client ID, Client Secret | https://github.com/settings/developers |

---

## 10. 状态码约定

| HTTP状态码 | 含义 |
|-----------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未认证/Token过期 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 429 | 请求频率超限 |
| 500 | 服务器内部错误 |