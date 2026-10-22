# Lotus Passport

[![CI](https://github.com/lotusor/lotus-passport/actions/workflows/ci.yml/badge.svg)](https://github.com/lotusor/lotus-passport/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Lotus Passport 是一个独立的统一身份认证中心：把 GitHub / QQ / 微信等第三方登录聚合为统一身份，向接入方签发可离线验证的 RS256 JWT。它只负责认证，不承载业务权限；接入方用 JWT 中的 `passport_user_id` 关联自己的用户。

## 功能

- OAuth 登录与账号绑定：GitHub、QQ、微信
- 授权码 + PKCE（OAuth 2.1 风格），令牌不经过 URL fragment
- RS256 签名 + JWKS 公钥分发 + 多 `kid` 密钥轮换
- 密码登录、邮箱验证码、密码找回、登录设备与会话管理
- Redis 限流、登录失败锁定、审计事件、服务端令牌吊销
- Python / JavaScript SDK，接入方无需共享签名密钥

## 架构

```text
┌──────────────┐      OAuth       ┌─────────────────────┐
│GitHub/QQ/微信 │◄────────────►   │  Lotus Passport API │
└──────────────┘                  │  Django + DRF       │
                                  │  RS256 + JWKS       │
┌──────────────┐    same-origin   │  Redis / PostgreSQL │
│ account SPA  │ ───────────────► └──────────┬──────────┘
│ Next.js      │                            │ JWT (RS256)
└──────────────┘                            ▼
                                  ┌─────────────────────┐
                                  │  接入方（如 E-algo） │
                                  │  SDK 离线验签        │
                                  └─────────────────────┘
```

## 仓库结构

| 路径 | 内容 |
|---|---|
| `lotus-passport/` | Django 认证后端（API、OAuth、JWT、账号安全） |
| `lotus-passport-security/` | Next.js 账号中心 SPA |
| `lotus-passport-sdk/` | Python 接入 SDK（RS256 + JWKS） |
| `lotus-passport-sdk-js/` | JavaScript / TypeScript 接入 SDK |
| `lotus-passport/docs/integration/` | 接入方契约文档 |
| `.github/` | CI、公开仓库门禁、Issue / PR 模板 |

## 快速开始

### 后端

```bash
git clone https://github.com/lotusor/lotus-passport.git
cd lotus-passport

python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
python -m pip install -r lotus-passport/requirements.txt

cp lotus-passport/.env.example lotus-passport/.env
# 按需修改 SECRET_KEY、TOKEN_ENCRYPTION_KEY 等；.env 已被 gitignore

cd lotus-passport
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

健康检查：`GET http://127.0.0.1:8000/api/v1/health/`。

### 账号中心 SPA

```bash
cd lotus-passport-security
cp .env.example .env.local
npm ci
npm run dev
```

打开 `http://127.0.0.1:3000/login`。本地开发默认开启 DEV 模拟登录；生产环境必须设置 `DEBUG=False` 且保持 `ENABLE_DEV_LOGIN=False`。

### 测试

```bash
cd lotus-passport
python -m pytest -q
```

Python SDK 与 JavaScript SDK 各有独立测试，详见各目录 README；CI 会同时运行后端、两个 SDK 和前端构建检查。

## 配置

所有配置通过环境变量注入。仓库只提交 `*.example` 模板，真实密钥、数据库密码、OAuth secret、SMTP 授权码一律不要入库。

关键变量：

| 变量 | 说明 |
|---|---|
| `DEBUG` | 生产必须为 `False` |
| `ENABLE_DEV_LOGIN` | 开发桩登录开关；生产必须为 `False` |
| `SECRET_KEY` | Django 密钥，生产使用强随机值 |
| `TOKEN_ENCRYPTION_KEY` | 第三方 token 的 AES-256-CBC 密钥 |
| `PASSPORT_JWT_PRIVATE_KEY` / `PASSPORT_JWT_PUBLIC_KEY` | 可选的 PEM 密钥注入方式 |
| `DATABASE_URL` / `REDIS_URL` | 数据库与 Redis 连接 |
| `CORS_ALLOWED_ORIGINS` / `OAUTH_ALLOWED_REDIRECT_URIS` | 接入方来源与回跳白名单 |

完整的开发、OAuth、RS256 与部署说明见 [`lotus-passport/README.md`](lotus-passport/README.md)。

## 安全

- 漏洞请通过 GitHub Security Advisories 私下报告，不要开公开 Issue；见 [SECURITY.md](SECURITY.md)。
- 仓库启用公开仓库门禁（`.github/scripts/check_public_repo.py`），拦截密钥、真实 `.env`、内部交接文档、构建缓存与公网 IP。
- 历史中若曾提交敏感内容，删除文件并不等于删除历史；处置流程见 [CONTRIBUTING.md](CONTRIBUTING.md) 与工作区规则。
- 生产部署请保持 `DEBUG=False`、`ENABLE_DEV_LOGIN=False`，使用强随机密钥、HTTPS 与最小权限数据库账号。

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。提交前请运行：

```bash
python .github/scripts/check_public_repo.py
cd lotus-passport && python -m pytest -q
cd ../lotus-passport-security && npm run build
```

## 许可证

[MIT](LICENSE)
