# Lotus Passport Web — 液态玻璃身份终端

Lotus Passport 统一认证中心的前端 SPA（Next.js 14 App Router + TypeScript）。
视觉方向：**OBSIDIAN TERMINAL** —— 黑曜石底 + 磷光绿液态玻璃 + 印章琥珀 + 信号红；
全站零渐变、零蓝紫；等宽体承担系统事实，Space Grotesk 承担人文语言。

> 本工程为从零重建的 MVP，与旧前端 `lotus-passport-security` 完全独立；
> 功能分区与后端接口契约保持一致，不改动任何后端代码。

## 快速开始

```bash
# 1) 后端（仓库内层目录，SQLite + fakeredis，零配置）
cd ../lotus-passport
python manage.py runserver 127.0.0.1:8000 --noreload

# 2) 前端
cp .env.example .env.local   # 默认 PASSPORT_API_ORIGIN=http://127.0.0.1:8000
npm install
npm run dev                  # http://localhost:3000
```

开发环境下后端 `ENABLE_DEV_LOGIN` 默认开启，登录页会出现 **DEV 模拟登录** 区块，
可走完整 `登录 → PKCE 授权码 → JWT → userinfo` 链路。

## 功能分区

| 路由 | 分区 | 对齐端点 |
|---|---|---|
| `/login` | 密码登录 / 邮箱验证码登录即注册 / OAuth / 找回密码 | `login/`、`login/email/`、`oauth/{p}/login/`、`security/password/reset-request/` |
| `/auth/callback` | PKCE 授权码换令牌 / fragment 兼容 / 绑定回跳 | `oauth/token/`、`userinfo/`、`oauth/continue/` |
| `/oauth/consent` | 外部应用授权确认（原生表单 POST） | `oauth/consent/` |
| `/login/password/reset` | 邮件一次性 token 重置密码 | `security/password/reset/` |
| `/account` | 总览：身份卡 + 安全态势 + 最近活动 | `profile/`、`security/password/`、`oauth/accounts/`、`devices/`、`sessions/`、`security/login-history/` |
| `/account/profile` | 资料编辑 + 头像上传（≤128KB） | `profile/` PATCH、`profile/avatar/` |
| `/account/security` | 密码设置/修改、邮箱绑定/双重验证换绑、注销 | `security/password/change/`、`security/email/*`、`profile/` DELETE |
| `/account/connections` | 第三方绑定/解绑（末位登录方式保护） | `oauth/{p}/bind/`、`oauth/{p}/` DELETE |
| `/account/devices` | 设备重命名 / 信任开关 / 撤销 | `devices/`、`devices/{id}/` |
| `/account/sessions` | 会话注销 / 批量注销其它 | `sessions/`、`sessions/{id}/` |
| `/account/activity` | 登录审计（最近 50 条，可筛选） | `security/login-history/` |

## 架构要点

- **同源代理**：`next.config.mjs` 把 `/api`、`/media`、`/.well-known` 重写到 `PASSPORT_API_ORIGIN`，
  浏览器只访问同源，与生产部署形态一致。
- **鉴权**：localStorage 存 access/refresh；401 单飞刷新重试一次；刷新失败广播 `lp:auth-expired`
  清退到登录页；侧栏实时显示 ACCESS 令牌倒计时并在临期自动续期。
- **PKCE**：OAuth 登录与 DEV 登录一律 S256 授权码模式；verifier 存 sessionStorage，回调单次消费。
- **动效**：终端 BIOS 启动 Loading（真实探测后端）、路由转场、滚动驱动背景视差与入场揭示；
  全部尊重 `prefers-reduced-motion`。
- **可访问性**：语义结构、可见焦点环、模态焦点陷阱、aria-live 通知、状态不只靠颜色。

## 构建

```bash
npm run typecheck   # tsc --noEmit
npm run build       # 生产构建
npm run start       # 生产服务（:3000）
```