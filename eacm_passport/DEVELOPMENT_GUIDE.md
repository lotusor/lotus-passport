# EACM Passport 通行证系统 — 开发文档与部署指南

> E时代ACM令牌通行证系统 (EACM Passport System)
> 版本：v2.0 纯认证版
> 更新日期：2026-07-20

---

## 目录

1. [项目概述](#1-项目概述)
2. [项目结构](#2-项目结构)
3. [环境要求与安装](#3-环境要求与安装)
4. [环境变量配置说明](#4-环境变量配置说明)
5. [数据库模型](#5-数据库模型)
6. [API 接口文档](#6-api-接口文档)
7. [认证流程详解](#7-认证流程详解)
8. [安全策略](#8-安全策略)
9. [OAuth 提供者配置指南](#9-oauth-提供者配置指南)
10. [集成指南（给接入方如 algo_rank）](#10-集成指南给接入方如-algo_rank)
11. [本地开发](#11-本地开发)
12. [生产部署](#12-生产部署)
13. [常见问题 FAQ](#13-常见问题-faq)

---

## 1. 项目概述

### 系统定位

EACM Passport 是一个**独立统一认证中心**，为 E时代ACM令牌（algo_rank）及未来其他项目提供集中式身份认证服务。系统作为第三方 OAuth 中间层，聚合微信、QQ、GitHub 等第三方登录渠道，签发统一 JWT 令牌供所有接入方信任和验证。

### 核心功能

| 功能 | 说明 |
|------|------|
| OAuth 第三方登录 | 支持微信（开放平台）、QQ 互联、GitHub OAuth Apps |
| JWT 令牌认证 | 基于 SimpleJWT 签发 access_token / refresh_token |
| 令牌刷新与注销 | Token 轮转 + 黑名单机制 |
| 用户资料管理 | 昵称、头像修改，第三方账号绑定/解绑 |
| AES-256-CBC 加密 | 第三方 OAuth Token 加密存储 |
| 集成包 | 一键集成脚本，接入方（如 algo_rank）可快速对接 |

### 技术栈

| 组件 | 技术选型 |
|------|---------|
| 后端框架 | Django 5.x / 6.x |
| API 框架 | Django REST Framework (DRF) |
| JWT 认证 | djangorestframework-simplejwt |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| 缓存/Session | Redis |
| 加密 | cryptography (AES-256-CBC) |
| CORS | django-cors-headers |
| HTTP 客户端 | requests |
| WSGI 服务器 | Gunicorn |
| 环境变量 | python-dotenv |

---

## 2. 项目结构

```
eacm_passport/
├── manage.py                          # Django 管理入口
├── requirements.txt                   # Python 依赖清单
├── .env                               # 环境变量配置（不入库）
├── db.sqlite3                         # SQLite 开发数据库
│
├── eacm_passport/                     # Django 项目配置包
│   ├── __init__.py
│   ├── settings.py                    # 全局配置（数据库、JWT、OAuth、CORS等）
│   ├── urls.py                        # 根 URL 路由
│   ├── wsgi.py                        # WSGI 应用入口
│   ├── asgi.py                        # ASGI 应用入口
│   └── exceptions.py                  # 自定义异常处理器（统一响应格式）
│
├── apps/                              # 业务应用目录
│   ├── __init__.py
│   │
│   ├── users/                         # 用户管理应用
│   │   ├── __init__.py
│   │   ├── apps.py                     # AppConfig
│   │   ├── models.py                   # User 自定义用户模型
│   │   ├── managers.py                # UserManager（支持无密码创建）
│   │   ├── serializers.py              # 用户资料序列化器
│   │   ├── views.py                   # UserProfileView、OAuthAccountsView
│   │   ├── urls.py                    # 用户路由（profile/、oauth-accounts/）
│   │   ├── admin.py                   # Django Admin 注册
│   │   └── migrations/                # 数据库迁移
│   │       ├── __init__.py
│   │       └── 0001_initial.py         # 创建 User 表
│   │
│   └── oauth/                          # OAuth 认证应用
│       ├── __init__.py
│       ├── apps.py                    # AppConfig
│       ├── models.py                  # OAuthAccount 模型 + AES 加密/解密函数
│       ├── serializers.py             # OAuth 请求序列化器
│       ├── views.py                   # OAuthLoginView、OAuthCallbackView、TokenRefreshView、LogoutView
│       ├── urls.py                     # 认证路由（login/、callback/、refresh/、logout/）
│       ├── admin.py                   # Django Admin 注册
│       └── providers/                  # OAuth 提供者实现（策略模式）
│           ├── __init__.py
│           ├── base.py                # OAuthProviderBase 抽象基类
│           ├── wechat.py              # 微信 OAuth 提供者
│           ├── qq.py                  # QQ OAuth 提供者
│           └── github.py             # GitHub OAuth 提供者
│
└── venv/                              # Python 虚拟环境（不入库）
```

---

## 3. 环境要求与安装

### Python 版本

- Python 3.10+（推荐 3.12）
- 已验证兼容 Python 3.14

### 依赖清单 (requirements.txt)

```
django>=5.0,<6.0
djangorestframework>=3.14
djangorestframework-simplejwt>=5.3
requests>=2.31
authlib>=1.3
django-cors-headers>=4.3
django-filter>=23.5
python-dotenv>=1.0
cryptography>=41.0
redis>=5.0
gunicorn>=21.2
```

### 安装步骤

**步骤 1：克隆项目**

```bash
cd d:\dev\项目2-通行证系统\eacm_passport
```

**步骤 2：创建虚拟环境**

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate
```

**步骤 3：安装依赖**

```bash
pip install -r requirements.txt
```

**步骤 4：配置环境变量**

复制 `.env` 文件并按需修改（详见第 4 节）：

```bash
# .env 已存在于项目根目录，直接编辑即可
```

**步骤 5：数据库迁移**

```bash
python manage.py migrate
```

**步骤 6：创建超级管理员**

```bash
python manage.py createsuperuser --nickname admin
```

> 注意：由于自定义用户模型使用 `id` 作为 `USERNAME_FIELD`，`createsuperuser` 命令可能需要额外参数。可直接使用 Django shell 创建：

```bash
python manage.py shell -c "
from apps.users.models import User
User.objects.create_superuser(password='your_password', nickname='admin')
"
```

---

## 4. 环境变量配置说明

所有环境变量均在 `.env` 文件中配置，由 `python-dotenv` 在启动时加载。

### 完整配置参考表

| 变量名 | 说明 | 默认值 | 示例 |
|--------|------|--------|------|
| **基础配置** | | | |
| `SECRET_KEY` | Django 密钥（生产环境必须修改） | `django-insecure-eacm-passport-dev-key-change-in-production` | `a7f3b2...（64位随机字符串）` |
| `DEBUG` | 调试模式（生产环境设为 False） | `True` | `False` |
| `ALLOWED_HOSTS` | 允许的主机名（逗号分隔） | `*` | `passport.example.com,api.example.com` |
| **数据库配置** | | | |
| `DB_ENGINE` | 数据库引擎 | `django.db.backends.sqlite3` | `django.db.backends.postgresql` |
| `DB_NAME` | 数据库名称 | `db.sqlite3`（相对路径） | `eacm_passport` |
| `DB_USER` | 数据库用户名 | （无，SQLite不需要） | `postgres` |
| `DB_PASSWORD` | 数据库密码 | （无） | `your_db_password` |
| `DB_HOST` | 数据库主机 | （无） | `localhost` |
| `DB_PORT` | 数据库端口 | （无） | `5432` |
| **JWT 配置** | | | |
| `JWT_ACCESS_TOKEN_LIFETIME` | Access Token 有效期（分钟） | `120` | `60` |
| `JWT_REFRESH_TOKEN_LIFETIME` | Refresh Token 有效期（秒） | `2592000`（30天） | `604800`（7天） |
| `JWT_SIGNING_KEY` | JWT 签名密钥（不设则用 SECRET_KEY） | `SECRET_KEY` | `your-jwt-signing-key` |
| **微信 OAuth** | | | |
| `WECHAT_APP_ID` | 微信开放平台 AppID | （空） | `wx1234567890abcdef` |
| `WECHAT_APP_SECRET` | 微信开放平台 AppSecret | （空） | `abcdef1234567890` |
| **QQ OAuth** | | | |
| `QQ_APP_ID` | QQ 互联 App ID | （空） | `101234567` |
| `QQ_APP_KEY` | QQ 互联 App Key | （空） | `abcdef1234567890abcdef` |
| **GitHub OAuth** | | | |
| `GITHUB_CLIENT_ID` | GitHub OAuth App Client ID | （空） | `Ov23abcdef123456` |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App Client Secret | （空） | `abcdef1234567890abcdef1234567890` |
| **安全配置** | | | |
| `AES_SECRET_KEY` | AES-256 加密密钥（**必须32字节**） | `dev-test-32-bytes-secret-key!!` | `your-production-32-byte-secret-key!!` |
| **CORS 配置** | | | |
| `CORS_ALLOWED_ORIGINS` | 允许的跨域来源（逗号分隔） | `http://localhost:8000,http://localhost:3000,http://localhost:5173` | `https://example.com,https://app.example.com` |
| **Redis 配置** | | | |
| `REDIS_URL` | Redis 连接地址 | `redis://localhost:6379/0` | `redis://:password@127.0.0.1:6379/0` |

### .env 完整示例

```env
# === 基础配置 ===
SECRET_KEY=eacm-passport-test-secret-key-for-dev-only
DEBUG=True
ALLOWED_HOSTS=*

# === 数据库 ===
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3

# === Redis ===
REDIS_URL=redis://localhost:6379/0

# === JWT ===
JWT_ACCESS_TOKEN_LIFETIME=120
JWT_REFRESH_TOKEN_LIFETIME=2592000

# === 微信 OAuth ===
WECHAT_APP_ID=
WECHAT_APP_SECRET=

# === QQ OAuth ===
QQ_APP_ID=
QQ_APP_KEY=

# === GitHub OAuth ===
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# === CORS ===
CORS_ALLOWED_ORIGINS=http://localhost:8000,http://localhost:3000,http://localhost:5173

# === 安全 ===
AES_SECRET_KEY=dev-test-32-bytes-secret-key!!
```

> **注意**：使用 PostgreSQL 时，需在 `settings.py` 中手动补充 `DB_USER`、`DB_PASSWORD`、`DB_HOST`、`DB_PORT` 的 `os.getenv` 读取逻辑，当前版本默认仅支持 `DB_ENGINE` 和 `DB_NAME`。

---

## 5. 数据库模型

### User 模型 (`apps.users.models.User`)

自定义用户模型，继承 `AbstractBaseUser` 和 `PermissionsMixin`。通过 OAuth 第三方登录创建，不依赖用户名和密码。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BigAutoField (PK) | 用户 ID，同时作为 `USERNAME_FIELD` |
| `nickname` | CharField(50) | 昵称，允许为空 |
| `avatar` | URLField(500) | 头像 URL，允许为空 |
| `is_staff` | BooleanField | Django 后台权限标记（非业务管理员） |
| `is_active` | BooleanField | 是否激活 |
| `created_at` | DateTimeField | 创建时间（auto_now_add） |
| `updated_at` | DateTimeField | 更新时间（auto_now） |
| `password` | CharField(128) | 继承自 AbstractBaseUser，OAuth 用户设为不可用 |

**关键字段说明：**

- `USERNAME_FIELD = 'id'` — 使用用户 ID 作为登录标识
- `REQUIRED_FIELDS = []` — 无必填字段
- OAuth 创建的用户密码通过 `set_unusable_password()` 设为不可用
- 属性 `oauth_providers`：返回已绑定的第三方登录方式列表

**数据库表名：** `eacm_user`

### OAuthAccount 模型 (`apps.oauth.models.OAuthAccount`)

第三方 OAuth 账号绑定记录，一个用户可绑定多个第三方账号。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BigAutoField (PK) | 记录 ID |
| `user` | ForeignKey(User) | 关联用户（CASCADE 删除） |
| `provider` | CharField(20) | 登录平台：`wechat`/`qq`/`github` |
| `provider_user_id` | CharField(128) | 第三方平台用户唯一标识 |
| `provider_username` | CharField(100) | 第三方平台用户名 |
| `access_token` | CharField(512) | 访问令牌（AES-256-CBC 加密存储） |
| `refresh_token` | CharField(512) | 刷新令牌（AES-256-CBC 加密存储） |
| `token_expires_at` | DateTimeField | 令牌过期时间 |
| `bound_at` | DateTimeField | 绑定时间（auto_now_add） |

**约束：**
- `unique_together = ('provider', 'provider_user_id')` — 同一平台同一用户只能绑定一次

**方法：**
- `set_access_token(token)` / `get_access_token()` — 加密存取 access_token
- `set_refresh_token(token)` / `get_refresh_token()` — 加密存取 refresh_token

**AES 加密细节：**
- 算法：AES-256-CBC
- 密钥：取自 `settings.AES_SECRET_KEY`，自动截断/填充至 32 字节
- IV：每次加密随机生成 16 字节
- 填充：PKCS7
- 存储：`base64(IV + ciphertext)`

**数据库表名：** `eacm_oauth_account`

### 数据库迁移命令

```bash
# 创建迁移
python manage.py makemigrations

# 执行迁移
python manage.py migrate

# 查看迁移状态
python manage.py showmigrations

# 回滚到指定迁移
python manage.py migrate oauth 0001
```

---

## 6. API 接口文档

### 统一响应格式

所有接口返回统一的 JSON 格式：

```json
{
  "code": 200,
  "message": "ok",
  "data": { ... }
}
```

### 统一错误响应格式

```json
{
  "code": 400,
  "message": "错误描述",
  "data": null
}
```

**状态码约定：**

| code | HTTP Status | 含义 |
|------|-------------|------|
| 200 | 200 | 成功 |
| 400 | 400 | 请求参数错误 |
| 401 | 401 | 未认证/Token 无效 |
| 402 | 402 | 功能未开放（保留） |
| 403 | 403 | 权限不足 |
| 404 | 404 | 资源不存在 |
| 409 | 409 | 冲突（如手机号重复，当前版本保留） |
| 500 | 500 | 服务器内部错误 |
| 502 | 502 | 第三方服务错误 |
| 503 | 503 | 服务未配置/未启用 |

---

### 6.1 POST /api/auth/login/{provider}/ — 发起 OAuth 登录

**权限：** AllowAny（无需认证）

**路径参数：**
| 参数 | 类型 | 说明 |
|------|------|------|
| `provider` | string | 登录平台：`wechat`、`qq`、`github` |

**请求体 (JSON)：**
```json
{
  "redirect_uri": "http://localhost:5173/auth/callback"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `redirect_uri` | string | 是 | 回调地址，前端接收授权码的页面 URL |

**成功响应 (200)：**
```json
{
  "code": 200,
  "message": "ok",
  "data": {
    "authorization_url": "https://open.weixin.qq.com/connect/oauth2/authorize?appid=xxx&redirect_uri=xxx&response_type=code&scope=snsapi_login&state=xxx",
    "state": "random_state_string_32_bytes"
  }
}
```

**错误响应：**
| code | message | 说明 |
|------|---------|------|
| 400 | 不支持的登录方式: xxx | provider 不在支持列表中 |
| 503 | {provider}登录服务暂未配置 | 未配置该平台的 App ID/Secret |

---

### 6.2 POST /api/auth/callback/{provider}/ — OAuth 回调

**权限：** AllowAny（无需认证）

**路径参数：**
| 参数 | 类型 | 说明 |
|------|------|------|
| `provider` | string | 登录平台 |

**请求体 (JSON)：**
```json
{
  "code": "authorization_code_from_oauth_provider",
  "state": "random_state_string_32_bytes",
  "redirect_uri": "http://localhost:5173/auth/callback"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | 是 | OAuth 提供者返回的授权码 |
| `state` | string | 是 | 登录时获取的 state 参数 |
| `redirect_uri` | string | 是 | 与登录时一致的回调地址 |

**成功响应 (200) — 已有用户：**
```json
{
  "code": 200,
  "message": "ok",
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "Bearer",
    "expires_in": 7200,
    "user": {
      "id": 1,
      "nickname": "张三",
      "avatar": "https://example.com/avatar.jpg"
    },
    "is_new_user": false
  }
}
```

**成功响应 (200) — 新用户：**
```json
{
  "code": 200,
  "message": "ok",
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "Bearer",
    "expires_in": 7200,
    "user": {
      "id": 2,
      "nickname": "",
      "avatar": ""
    },
    "is_new_user": true
  }
}
```

**错误响应：**
| code | message | 说明 |
|------|---------|------|
| 400 | 不支持的登录方式: xxx | provider 无效 |
| 400 | state无效或已过期，请重新登录 | state 不存在或已超时（600秒） |
| 400 | 回调参数不匹配 | state 中记录的 provider/redirect_uri 与请求不一致 |
| 502 | 第三方认证失败: {detail} | OAuth 提供者返回错误 |
| 500 | 认证过程中发生错误 | 未知异常 |

---

### 6.3 POST /api/auth/refresh/ — 刷新 JWT 令牌

**权限：** AllowAny（无需认证）

**请求体 (JSON)：**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `refresh_token` | string | 是 | 登录/上次刷新时获取的 refresh_token |

**成功响应 (200)：**
```json
{
  "code": 200,
  "message": "ok",
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "Bearer",
    "expires_in": 7200
  }
}
```

> **注意**：由于启用了 `ROTATE_REFRESH_TOKENS = True`，每次刷新都会生成新的 refresh_token，旧的 refresh_token 自动加入黑名单。

**错误响应：**
| code | message | 说明 |
|------|---------|------|
| 401 | 令牌刷新失败: {detail} | refresh_token 无效、过期或已被拉黑 |

---

### 6.4 POST /api/auth/logout/ — 注销

**权限：** IsAuthenticated（需要 Bearer Token）

**请求头：**
```
Authorization: Bearer {access_token}
```

**请求体 (JSON)：**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `refresh_token` | string | 是 | 需要注销的 refresh_token |

**成功响应 (200)：**
```json
{
  "code": 200,
  "message": "已注销",
  "data": null
}
```

> 注销操作会将 refresh_token 加入黑名单。access_token 在其有效期到期前仍然可用（JWT 无状态特性），但已无法用于刷新。

---

### 6.5 GET /api/user/profile/ — 获取用户资料

**权限：** IsAuthenticated（需要 Bearer Token）

**请求头：**
```
Authorization: Bearer {access_token}
```

**成功响应 (200)：**
```json
{
  "code": 200,
  "message": "ok",
  "data": {
    "id": 1,
    "nickname": "张三",
    "avatar": "https://example.com/avatar.jpg",
    "is_staff": false,
    "oauth_providers": ["wechat", "github"],
    "created_at": "2026-07-19T17:20:00+08:00"
  }
}
```

---

### 6.6 PUT/PATCH /api/user/profile/ — 更新用户资料

**权限：** IsAuthenticated（需要 Bearer Token）

**请求头：**
```
Authorization: Bearer {access_token}
```

**请求体 (JSON)：**
```json
{
  "nickname": "新昵称",
  "avatar": "https://example.com/new-avatar.jpg"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `nickname` | string | 否 | 昵称，最长50字符，可为空 |
| `avatar` | string | 否 | 头像 URL，最长500字符，可为空 |

> `PUT` 要求提供所有字段，`PATCH` 只需提供要修改的字段。

**成功响应 (200)：**
```json
{
  "code": 200,
  "message": "ok",
  "data": {
    "id": 1,
    "nickname": "新昵称",
    "avatar": "https://example.com/new-avatar.jpg",
    "is_staff": false,
    "oauth_providers": ["wechat", "github"],
    "created_at": "2026-07-19T17:20:00+08:00"
  }
}
```

---

### 6.7 GET /api/user/oauth-accounts/ — 查看第三方账号

**权限：** IsAuthenticated（需要 Bearer Token）

**请求头：**
```
Authorization: Bearer {access_token}
```

**成功响应 (200)：**
```json
{
  "code": 200,
  "message": "ok",
  "data": [
    {
      "provider": "wechat",
      "provider_username": "张三",
      "bound_at": "2026-07-19T17:20:00+08:00"
    },
    {
      "provider": "github",
      "provider_username": "zhangsan",
      "bound_at": "2026-07-19T18:00:00+08:00"
    }
  ]
}
```

---

### 6.8 DELETE /api/user/oauth-accounts/{provider}/ — 解绑第三方账号

**权限：** IsAuthenticated（需要 Bearer Token）

**路径参数：**
| 参数 | 类型 | 说明 |
|------|------|------|
| `provider` | string | 要解绑的平台：`wechat`、`qq`、`github` |

**成功响应 (200)：**
```json
{
  "code": 200,
  "message": "已解绑wechat账号",
  "data": null
}
```

**错误响应：**
| code | message | 说明 |
|------|---------|------|
| 400 | 不支持的第三方平台 | provider 不是 wechat/qq/github |
| 400 | 至少保留一个第三方登录方式 | 用户只剩一个绑定 |
| 404 | 未绑定该第三方账号 | 用户未绑定该平台 |

---

## 7. 认证流程详解

### 7.1 完整 OAuth 登录时序

```
用户          前端应用          EACM Passport         OAuth提供者
 |              |                   |                     |
 |-- 1.点击登录 -->|                  |                     |
 |              |-- 2.POST login -->|                     |
 |              |<-- authorization_url, state --|          |
 |              |                   |                     |
 |<-- 3.跳转到OAuth授权页 --|       |                     |
 |-- 4.授权 ---------->|             |                     |
 |              |                   |                     |
 |              |<-- 5.携带code回调 --|                     |
 |              |                   |                     |
 |              |-- 6.POST callback(code,state,redirect_uri) -->|
 |              |                   |-- 7.验证state(缓存)    |
 |              |                   |-- 8.验证provider匹配  |
 |              |                   |-- 9.用code换token  -->|
 |              |                   |<-- access_token ----|
 |              |                   |-- 10.获取用户信息  -->|
 |              |                   |<-- userinfo -------|
 |              |                   |                     |
 |              |                   |-- 11.查找/创建用户   |
 |              |                   |-- 12.签发JWT         |
 |              |<-- JWT + 用户信息 --|                    |
 |              |                   |                     |
 |<-- 13.登录完成，存储JWT --|       |                     |
```

### 7.2 详细步骤说明

1. **用户发起登录**：用户在前端点击"微信/QQ/GitHub 登录"按钮
2. **获取授权 URL**：前端调用 `POST /api/auth/login/{provider}/`，传入 `redirect_uri`；后端生成 `state`（随机安全字符串），存入 Redis 缓存（600秒过期），返回第三方授权 URL
3. **跳转授权**：前端将用户重定向到第三方授权页面
4. **用户授权**：用户在第三方页面确认授权
5. **回调前端**：第三方将用户重定向回 `redirect_uri`，携带 `code` 和 `state` 参数
6. **提交回调**：前端将 `code`、`state`、`redirect_uri` 发送到 `POST /api/auth/callback/{provider}/`
7. **验证 state**：从 Redis 读取 state 对应的数据，验证存在且匹配
8. **验证参数匹配**：确认 state 中记录的 provider 和 redirect_uri 与请求一致
9. **换取 token**：用 code 向第三方提供者请求 access_token
10. **获取用户信息**：用 access_token 向第三方请求用户信息
11. **查找/创建用户**：
    - **老用户**：根据 `provider + provider_user_id` 查找已有绑定，更新 token 和用户名
    - **新用户**：创建 User（密码设为不可用）+ OAuthAccount 绑定记录
12. **签发 JWT**：使用 SimpleJWT 签发 access_token 和 refresh_token
13. **返回结果**：前端存储 JWT，完成登录

### 7.3 新用户 vs 老用户处理逻辑

| 场景 | 处理方式 | is_new_user |
|------|---------|-------------|
| 已有绑定记录 | 更新 token、用户名、过期时间，返回已有用户信息 | `false` |
| 全新用户 | 创建 User + OAuthAccount，设置不可用密码 | `true` |

### 7.4 状态码约定

| 接口 | code | 场景 |
|------|------|------|
| login | 200 | 成功返回授权 URL |
| login | 400 | 不支持的 provider |
| login | 503 | OAuth 服务未配置 |
| callback | 200 | 登录成功 |
| callback | 400 | state 无效/过期/不匹配 |
| callback | 502 | 第三方认证失败 |
| callback | 500 | 未知异常 |
| refresh | 200 | 刷新成功 |
| refresh | 401 | refresh_token 无效 |
| logout | 200 | 注销成功 |
| profile GET | 200 | 获取成功 |
| profile PUT/PATCH | 200 | 更新成功 |
| oauth-accounts GET | 200 | 获取成功 |
| oauth-accounts DELETE | 200 | 解绑成功 |
| oauth-accounts DELETE | 400 | 不支持的平台/不能全部解绑 |
| oauth-accounts DELETE | 404 | 未绑定该平台 |

---

## 8. 安全策略

### 8.1 JWT 安全

| 策略 | 配置 | 说明 |
|------|------|------|
| 签名算法 | `HS256` | 对称加密，性能好 |
| 签名密钥 | `JWT_SIGNING_KEY`（默认 `SECRET_KEY`） | 生产环境建议独立设置 |
| Token 轮转 | `ROTATE_REFRESH_TOKENS = True` | 每次刷新生成新 refresh_token |
| 黑名单 | `BLACKLIST_AFTER_ROTATION = True` | 旧 refresh_token 立即失效 |
| access_token 有效期 | 默认 120 分钟 | 可通过 `JWT_ACCESS_TOKEN_LIFETIME` 调整 |
| refresh_token 有效期 | 默认 30 天 | 可通过 `JWT_REFRESH_TOKEN_LIFETIME` 调整 |
| 认证头 | `Bearer` | `Authorization: Bearer <token>` |
| 用户标识字段 | `user_id` | JWT payload 中的用户 ID 字段 |

### 8.2 OAuth 安全

| 策略 | 实现 |
|------|------|
| CSRF 防护 — state 参数 | 每次登录生成 `secrets.token_urlsafe(32)` 随机 state，存入 Redis，回调时验证 |
| state 过期 | 600 秒后自动失效，一次性使用（验证后立即删除） |
| Token 加密存储 | AES-256-CBC 加密后 base64 存储 access_token 和 refresh_token |
| 参数匹配验证 | state 中记录的 provider 和 redirect_uri 必须与回调请求完全一致 |
| 密码策略 | OAuth 用户使用 `set_unusable_password()`，无法通过密码登录 |

### 8.3 接口限流

| 类型 | 限流 | 说明 |
|------|------|------|
| 匿名用户 | 60 次/分钟 | `anon` 限流类 |
| 已认证用户 | 120 次/分钟 | `user` 限流类 |
| 短信接口 | 10 次/小时 | `sms` 限流类（当前版本保留配置，未实际使用） |

### 8.4 CORS 策略

| 模式 | 配置 | 说明 |
|------|------|------|
| 开发模式（DEBUG=True） | `CORS_ALLOW_ALL_ORIGINS = True` | 允许所有来源 |
| 生产模式（DEBUG=False） | `CORS_ALLOWED_ORIGINS` 白名单 | 仅允许配置的域名 |
| 凭证 | `CORS_ALLOW_CREDENTIALS = True` | 允许携带 Cookie/Authorization |

### 8.5 密码安全

- OAuth 创建的用户调用 `set_unusable_password()`，密码字段设为不可用哈希值
- 超级管理员通过 `createsuperuser` 创建，使用 `set_password()` 设置强密码
- Django 内置密码验证器已启用（长度、相似度、常用密码、纯数字检查）

---

## 9. OAuth 提供者配置指南

### 9.1 微信开放平台

**申请流程：**
1. 访问 [微信开放平台](https://open.weixin.qq.com/) 并注册开发者账号
2. 创建"网站应用"（用于 PC 端扫码登录）
3. 提交审核，获取 **AppID** 和 **AppSecret**

**回调域名配置：**
- 在微信开放平台 → 管理中心 → 网站应用 → 授权回调域
- 填写你的通行证服务域名（如 `passport.example.com`）
- 微信回调 URL 模式：前端页面 URL（如 `https://passport.example.com/login/callback`）

**环境变量配置：**
```env
WECHAT_APP_ID=wx_your_app_id
WECHAT_APP_SECRET=your_app_secret
```

**授权流程特点：**
- 授权 URL：`https://open.weixin.qq.com/connect/oauth2/authorize`
- Scope：`snsapi_login`（扫码登录）
- Token URL：`https://api.weixin.qq.com/sns/oauth2/access_token`
- 用户信息 URL：`https://api.weixin.qq.com/sns/userinfo`
- 返回字段：`openid`（用户唯一标识）、`nickname`、`headimgurl`

### 9.2 QQ 互联

**申请流程：**
1. 访问 [QQ 互联](https://connect.qq.com/) 并注册开发者账号
2. 创建"网站应用"
3. 提交审核，获取 **APP ID** 和 **APP Key**

**回调地址配置：**
- QQ 互联 → 应用管理 → 网站应用 → 回调地址
- 填写前端页面完整 URL（如 `https://passport.example.com/login/callback`）

**环境变量配置：**
```env
QQ_APP_ID=your_qq_app_id
QQ_APP_KEY=your_qq_app_key
```

**授权流程特点：**
- 授权 URL：`https://graph.qq.com/oauth2.0/authorize`
- Scope：`get_user_info`
- Token 返回格式：`text/plain`（需特殊解析 `key=value&key=value`）
- 需两步获取用户信息：先获取 `openid`，再获取用户详情
- OpenID 返回格式：`callback( {"client_id":"...","openid":"..."} )`

### 9.3 GitHub OAuth Apps

**创建流程：**
1. 访问 GitHub → Settings → Developer settings → OAuth Apps
2. 点击 "New OAuth App"
3. 填写：
   - **Application name**：EACM Passport
   - **Homepage URL**：`https://passport.example.com`
   - **Authorization callback URL**：前端页面 URL（如 `https://passport.example.com/login/callback`）
4. 创建后获取 **Client ID** 和 **Client Secret**

**环境变量配置：**
```env
GITHUB_CLIENT_ID=Ov23_xxxxxxxxxx
GITHUB_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**授权流程特点：**
- 授权 URL：`https://github.com/login/oauth/authorize`
- Scope：`read:user,user:email`
- Token 交换方式：POST + JSON body + `Accept: application/json`
- 用户信息：通过 `Authorization: Bearer` 请求 `https://api.github.com/user`
- 用户标识：GitHub 用户数字 ID（转为字符串存储）

---

## 10. 集成指南（给接入方如 algo_rank）

### 10.1 一键集成脚本

集成包位于 `d:\dev\项目2-通行证系统\integration-package\`。

**使用方法：**

```bash
# 进入 algo_rank 项目所在目录
cd d:\dev\项目1-爬虫项目

# 运行集成脚本
python d:\dev\项目2-通行证系统\integration-package\apply_integration.py
```

**脚本自动完成以下操作：**
1. 修改 `config/settings.py` — 添加通行证配置段（`EACM_PASSPORT_*` 变量）
2. 修改 `apps/auth_app/models.py` — 添加 `passport_user_id`、`passport_nickname`、`passport_avatar`、`login_method` 字段
3. 修改 `apps/auth_app/urls.py` — 添加通行证路由
4. 复制模块文件到 algo_rank（`passport_client.py`、`passport_views.py`、`passport_serializers.py`）
5. 创建 `passport_urls.py` 路由文件
6. 修改 `.env` — 添加通行证环境变量
7. 修改 `requirements.txt` — 添加 `cryptography` 依赖
8. 自动生成并应用数据库迁移

### 10.2 集成包文件说明

| 文件 | 用途 | 放置位置 |
|------|------|---------|
| `apply_integration.py` | 一键集成脚本 | 在 algo_rank 外部运行 |
| `passport_client.py` | 通行证 HTTP 客户端（验证 token、转发请求） | `apps/auth_app/passport_client.py` |
| `passport_views.py` | 通行证认证视图（登录、回调、绑定学校、Token登录） | `apps/auth_app/passport_views.py` |
| `passport_serializers.py` | 通行证请求序列化器 | `apps/auth_app/passport_serializers.py` |
| `test_integration.py` | 集成测试脚本 | 在通行证系统外部运行 |

### 10.3 手动集成步骤

如果不想使用一键脚本，可手动执行以下步骤：

**步骤 1：添加环境变量**

在接入方 `.env` 中添加：
```env
EACM_PASSPORT_ENABLED=True
EACM_PASSPORT_BASE_URL=http://localhost:8001
EACM_PASSPORT_CLIENT_ID=algo_rank
EACM_PASSPORT_CLIENT_SECRET=algo_rank_secret_change_in_production
EACM_PASSPORT_CALLBACK_URL=http://localhost:8000/api/v1/auth/passport/callback/
```

**步骤 2：修改 settings.py**

```python
# EACM 通行证集成配置
EACM_PASSPORT_ENABLED = os.getenv('EACM_PASSPORT_ENABLED', 'True').lower() in ('true', '1', 'yes')
EACM_PASSPORT_BASE_URL = os.getenv('EACM_PASSPORT_BASE_URL', 'http://localhost:8001').rstrip('/')
EACM_PASSPORT_CLIENT_ID = os.getenv('EACM_PASSPORT_CLIENT_ID', '')
EACM_PASSPORT_CLIENT_SECRET = os.getenv('EACM_PASSPORT_CLIENT_SECRET', '')
EACM_PASSPORT_CALLBACK_URL = os.getenv('EACM_PASSPORT_CALLBACK_URL', '')
EACM_PASSPORT_TOKEN_VERIFY_TIMEOUT = 10

# Token 黑名单支持
if 'rest_framework_simplejwt.token_blacklist' not in INSTALLED_APPS:
    INSTALLED_APPS.insert(
        INSTALLED_APPS.index('rest_framework_simplejwt') + 1,
        'rest_framework_simplejwt.token_blacklist',
    )
```

**步骤 3：User 模型添加字段**

```python
# EACM 通行证关联字段
passport_user_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name='通行证用户ID')
passport_nickname = models.CharField(max_length=50, blank=True, default='', verbose_name='通行证昵称')
passport_avatar = models.URLField(max_length=500, blank=True, default='', verbose_name='通行证头像')
login_method = models.CharField(max_length=20, blank=True, default='local', verbose_name='登录方式')
```

**步骤 4：复制集成模块文件并添加路由**

将 `passport_client.py`、`passport_views.py`、`passport_serializers.py` 复制到接入方的 `apps/auth_app/` 目录，并在 `urls.py` 中添加路由。

**步骤 5：运行迁移**

```bash
python manage.py makemigrations auth_app
python manage.py migrate
```

### 10.4 集成后新增 API 接口

集成完成后，接入方将新增以下接口：

| 接口 | 说明 |
|------|------|
| `POST /api/v1/auth/passport/login/<provider>/` | 发起通行证 OAuth 登录 |
| `POST /api/v1/auth/passport/callback/<provider>/` | OAuth 回调（新用户返回 `need_bind_school`） |
| `POST /api/v1/auth/passport/bind-school/` | 新用户绑定学校并完成注册 |
| `POST /api/v1/auth/passport/token-login/` | 通过通行证 Token 直接登录 |

### 10.5 双模式认证共存策略

集成后，接入方同时支持两种登录方式：

| 模式 | 说明 | `login_method` 标记 |
|------|------|---------------------|
| 本地认证 | 原有的用户名/密码登录 | `local` |
| 通行证认证 | 通过 EACM Passport OAuth 登录 | `passport` |

**共存策略：**
- 用户通过通行证首次登录时，在接入方创建本地用户记录，`passport_user_id` 关联通行证 ID
- 本地用户可通过 `passport_user_id` 字段关联通行证账号
- 两种登录方式各自签发独立的 JWT（接入方使用自己的 JWT 密钥）
- 通行证 Token 只用于跨系统身份验证，不替代接入方自身的认证体系

**新用户注册流程（通行证方式）：**
1. 用户通过 OAuth 授权 → 通行证签发 Token
2. 接入方验证 Token → 获取通行证用户信息
3. 若新用户 → 返回 `need_bind_school: true` + `passport_token`
4. 前端展示学校选择界面 → 用户选择学校
5. 调用 `bind-school/` → 接入方创建本地用户 + 关联通行证
6. 接入方签发自己的 JWT → 登录完成

---

## 11. 本地开发

### 启动开发服务器

```bash
cd d:\dev\项目2-通行证系统\eacm_passport
venv\Scripts\activate          # Windows
python manage.py runserver 0.0.0.0:8001
```

服务默认监听 `http://localhost:8001`。

### Django Admin 访问

```
http://localhost:8001/admin/
```

使用创建的超级管理员账号登录。可管理：
- **用户**（User）：查看用户列表、昵称、状态
- **第三方账号绑定**（OAuth Account）：查看绑定记录（token 为加密存储）

### 创建测试数据

```bash
# 进入 Django Shell
python manage.py shell

# 创建测试用户
from apps.users.models import User
user = User.objects.create_user(nickname='测试用户')
print(f"创建用户: {user}")

# 查看用户信息
print(f"ID: {user.id}, 昵称: {user.nickname}, OAuth登录方式: {user.oauth_providers}")

# 检查密码状态
print(f"密码可用: {user.has_usable_password()}")  # 应输出 False

# 创建超级管理员
admin = User.objects.create_superuser(password='admin123', nickname='管理员')
```

### 运行集成测试

```bash
cd d:\dev\项目2-通行证系统
python integration-package\test_integration.py
```

---

## 12. 生产部署

### 12.1 服务器推荐

| 配置 | 最低要求 | 推荐配置 |
|------|---------|---------|
| 操作系统 | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| CPU | 1 核 | 2 核 |
| 内存 | 1 GB | 2 GB |
| 磁盘 | 20 GB SSD | 40 GB SSD |

### 12.2 部署步骤概览

```bash
# 1. 克隆代码
git clone <repository_url> /opt/eacm_passport
cd /opt/eacm_passport

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置 .env（参考第 4 节）
cp .env.example .env
vim .env  # 编辑配置

# 5. 数据库迁移
python manage.py migrate

# 6. 收集静态文件
python manage.py collectstatic --noinput

# 7. 创建超级管理员
python manage.py shell -c "
from apps.users.models import User
User.objects.create_superuser(password='YOUR_ADMIN_PASSWORD', nickname='admin')
"
```

### 12.3 Gunicorn 配置

创建 `/opt/eacm_passport/gunicorn.conf.py`：

```python
import multiprocessing

bind = '127.0.0.1:8001'
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'gthread'
threads = 2
timeout = 120
keepalive = 5

accesslog = '/var/log/eacm_passport/gunicorn_access.log'
errorlog = '/var/log/eacm_passport/gunicorn_error.log'
loglevel = 'info'

# Django WSGI
wsgi_app = 'eacm_passport.wsgi:application'
raw_env = ['DJANGO_SETTINGS_MODULE=eacm_passport.settings']
```

启动命令：
```bash
/home/your_user/.local/bin/gunicorn \
    -c gunicorn.conf.py \
    eacm_passport.wsgi:application
```

### 12.4 Nginx 配置

创建 `/etc/nginx/sites-available/eacm_passport`：

```nginx
server {
    listen 80;
    server_name passport.example.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name passport.example.com;

    ssl_certificate /etc/letsencrypt/live/passport.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/passport.example.com/privkey.pem;

    # SSL 优化
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # 安全头
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # 静态文件
    location /static/ {
        alias /opt/eacm_passport/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 代理到 Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_read_timeout 120s;
    }

    # 上传大小限制
    client_max_body_size 10M;
}
```

启用配置：
```bash
ln -s /etc/nginx/sites-available/eacm_passport /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### 12.5 Supervisor 配置

创建 `/etc/supervisor/conf.d/eacm_passport.conf`：

```ini
[program:eacm_passport]
directory=/opt/eacm_passport
command=/opt/eacm_passport/venv/bin/gunicorn -c gunicorn.conf.py eacm_passport.wsgi:application
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/eacm_passport/supervisor.log
environment=DJANGO_SETTINGS_MODULE="eacm_passport.settings"
```

管理命令：
```bash
supervisorctl reread
supervisorctl update
supervisorctl status eacm_passport
supervisorctl restart eacm_passport
```

### 12.6 HTTPS (Let's Encrypt)

```bash
# 安装 certbot
apt install certbot python3-certbot-nginx

# 获取证书（首次）
certbot --nginx -d passport.example.com

# 自动续期（certbot 已自动设置 cron）
certbot renew --dry-run  # 测试续期
```

### 12.7 Redis 配置

```bash
# 安装 Redis
apt install redis-server

# 配置 Redis
vim /etc/redis/redis.conf

# 关键配置项：
# bind 127.0.0.1          # 仅本地访问
# port 6379
# requirepass your_redis_password
# maxmemory 256mb
# maxmemory-policy allkeys-lru

# 重启 Redis
systemctl restart redis-server
systemctl enable redis-server

# 验证连接
redis-cli ping  # 应返回 PONG
```

**.env 中的 Redis 配置：**
```env
REDIS_URL=redis://:your_redis_password@127.0.0.1:6379/0
```

### 12.8 生产环境 Checklist

| 检查项 | 要求 | 状态 |
|--------|------|------|
| `DEBUG=False` | 生产环境必须关闭 | [ ] |
| `SECRET_KEY` | 使用强随机密钥（64+字符） | [ ] |
| `ALLOWED_HOSTS` | 仅包含实际域名 | [ ] |
| `JWT_SIGNING_KEY` | 独立于 SECRET_KEY 的签名密钥 | [ ] |
| `AES_SECRET_KEY` | 32 字节随机密钥 | [ ] |
| `CORS_ALLOWED_ORIGINS` | 白名单模式（DEBUG=False 时生效） | [ ] |
| 数据库 | 使用 PostgreSQL 替代 SQLite | [ ] |
| Redis | 配置密码、禁止外部访问 | [ ] |
| HTTPS | 使用 Let's Encrypt 证书 | [ ] |
| Nginx | 配置安全头、静态文件缓存 | [ ] |
| 日志 | 配置 Gunicorn access/error 日志轮转 | [ ] |
| 防火墙 | 仅开放 80/443 端口 | [ ] |
| 静态文件 | 执行 `collectstatic` | [ ] |
| OAuth 回调 | 确保回调 URL 与第三方平台配置一致 | [ ] |
| 定时备份 | 数据库定期备份方案 | [ ] |

---

## 13. 常见问题 FAQ

### Q1: 启动时提示 Redis 连接失败

**原因**：Redis 未启动或连接地址配置错误。

**解决**：
1. 检查 Redis 是否运行：`redis-cli ping`
2. 检查 `.env` 中 `REDIS_URL` 配置是否正确
3. 如果暂时不需要 Redis（仅开发环境），可以使用 Django 的本地内存缓存作为临时方案（需修改 `settings.py` 添加 cache 配置回退）

### Q2: OAuth 登录提示"服务暂未配置"

**原因**：对应的 OAuth App ID/Secret 未在 `.env` 中配置。

**解决**：
1. 在对应的第三方平台（微信/QQ/GitHub）创建应用
2. 获取 App ID 和 Secret
3. 填入 `.env` 对应变量
4. 重启服务

### Q3: 微信登录回调提示 state 无效

**原因**：state 存储在 Redis 中，可能 Redis 连接断开导致丢失。

**解决**：
1. 检查 Redis 连接是否正常
2. 检查 `OAUTH_STATE_EXPIRES` 配置（默认 600 秒），是否用户操作太慢导致过期
3. 重新发起登录

### Q4: QQ 登录获取用户信息失败

**原因**：QQ 互联的 Token 响应为 `text/plain` 格式（`access_token=xxx&expires_in=xxx`），而非标准 JSON。

**解决**：本系统已在 `QQProvider.exchange_token()` 中处理了这种格式。如果仍然失败：
1. 确认 QQ 互联应用的 `APP ID` 和 `APP Key` 正确
2. 确认回调地址与 QQ 互联配置一致
3. 检查 QQ 互联应用是否已通过审核

### Q5: JWT Token 刷新返回 401

**原因**：refresh_token 已过期或已被加入黑名单。

**解决**：
1. 检查 refresh_token 是否在有效期内（默认 30 天）
2. 检查是否已经调用过 logout（会使 token 加入黑名单）
3. 检查是否已使用该 refresh_token 刷新过（轮转机制下旧 token 失效）
4. 如果以上都不是，检查 `JWT_SIGNING_KEY` 是否一致

### Q6: 如何添加新的 OAuth 提供者？

**步骤**：

1. 在 `apps/oauth/providers/` 下创建新的提供者文件（如 `google.py`）：

```python
from .base import OAuthProviderBase
from .wechat import OAuthError
import requests

class GoogleProvider(OAuthProviderBase):
    provider_name = 'google'

    def get_authorize_params(self, redirect_uri, state):
        return {
            'client_id': self.app_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': self.scope,
            'state': state,
            'access_type': 'offline',
        }

    def exchange_token(self, code, redirect_uri):
        resp = requests.post(
            self.token_url,
            data={
                'code': code,
                'client_id': self.app_id,
                'client_secret': self.app_secret,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            },
            headers={'Accept': 'application/json'},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if 'error' in data:
            raise OAuthError(f"Google token交换失败: {data.get('error_description')}")
        return data

    def get_user_info(self, token_response):
        access_token = token_response.get('access_token')
        resp = requests.get(
            self.userinfo_url,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            'provider_user_id': data['sub'],
            'nickname': data.get('name', ''),
            'avatar': data.get('picture', ''),
        }
```

2. 在 `settings.py` 的 `OAUTH_CONFIG` 中添加配置：

```python
'google': {
    'app_id': os.getenv('GOOGLE_CLIENT_ID', ''),
    'app_secret': os.getenv('GOOGLE_CLIENT_SECRET', ''),
    'authorize_url': 'https://accounts.google.com/o/oauth2/v2/auth',
    'token_url': 'https://oauth2.googleapis.com/token',
    'userinfo_url': 'https://www.googleapis.com/oauth2/v2/userinfo',
    'scope': 'openid profile email',
},
```

3. 在 `apps/oauth/views.py` 的 `PROVIDER_REGISTRY` 中注册：

```python
from .providers.google import GoogleProvider

PROVIDER_REGISTRY = {
    'wechat': WeChatProvider,
    'qq': QQProvider,
    'github': GitHubProvider,
    'google': GoogleProvider,
}
```

4. 在 `OAuthAccount.PROVIDER_CHOICES` 中添加选项。

### Q7: 如何从 SQLite 迁移到 PostgreSQL？

1. 安装 PostgreSQL 客户端库：`pip install psycopg2-binary`
2. 修改 `.env`：
```env
DB_ENGINE=django.db.backends.postgresql
DB_NAME=eacm_passport
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```
3. 修改 `settings.py` 的 `DATABASES` 配置，补充 `USER`、`PASSWORD`、`HOST`、`PORT`：
```python
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.getenv('DB_NAME', BASE_DIR / 'db.sqlite3'),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', ''),
        'PORT': os.getenv('DB_PORT', ''),
    }
}
```
4. 创建 PostgreSQL 数据库：`createdb eacm_passport`
5. 运行迁移：`python manage.py migrate`
6. 如需迁移数据，使用 `python manage.py dumpdata` + `loaddata` 或专业工具如 `pgloader`

### Q8: 如何重置开发环境？

```bash
# 删除数据库
rm db.sqlite3

# 删除迁移记录
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete

# 重新迁移
python manage.py makemigrations users oauth
python manage.py migrate

# 创建管理员
python manage.py shell -c "
from apps.users.models import User
User.objects.create_superuser(password='admin123', nickname='admin')
"
```

### Q9: 集成脚本执行失败怎么办？

1. 确认 algo_rank 项目路径正确（脚本中硬编码为 `d:\dev\项目1-爬虫项目\algo_rank`）
2. 如路径不同，修改 `apply_integration.py` 中的 `ALGO_RANK_DIR` 变量
3. 确认 algo_rank 虚拟环境已激活
4. 检查是否有文件已存在（脚本会跳过已修改的文件，标记 `[SKIP]`）
5. 如果部分步骤失败，可手动完成对应步骤（参考 10.3 节）

### Q10: 生产环境 CORS 报错

**原因**：`DEBUG=False` 时 `CORS_ALLOW_ALL_ORIGINS=False`，需要在 `CORS_ALLOWED_ORIGINS` 中显式配置白名单。

**解决**：在 `.env` 中添加所有需要跨域访问的前端域名：
```env
CORS_ALLOWED_ORIGINS=https://app.example.com,https://www.example.com
```

---

> 文档结束。如有疑问请联系开发团队。
