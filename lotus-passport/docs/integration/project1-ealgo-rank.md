# Lotus Passport 集成参考 — 项目1（e-algo rank / rank.eacm.cn）

> 本文件是**本地参考文档**，供项目1（e-algo rank，前端/回调用 `rank.eacm.cn`）后续开发时阅读。
> 由 Lotus Passport（统一身份认证服务）维护方编写，记录项目1 接入统一登录所需的契约。
> 项目1 **只消费**下面列出的端点与声明，无需关心 passport 内部实现。

---

## 1. 你已经预置好的东西（无需再改 passport 配置）

passport 侧已为项目1 预留白名单，直接可用：

| 类别 | 已放行值 | 来源 |
|---|---|---|
| CORS 来源 | `https://rank.eacm.cn` | `CORS_ALLOWED_ORIGINS`（settings.py） |
| OAuth 回调白名单 | `https://rank.eacm.cn` | `OAUTH_ALLOWED_REDIRECT_URIS`（settings.py） |

即：项目1 的前端/回调用 `rank.eacm.cn` 即可通过 CORS 与 OAuth 开放重定向校验，
**不用再找 passport 维护者改配置**。如需新增子路径回调（如 `https://rank.eacm.cn/callback/oauth`），
白名单是 origin 级（放行该 origin 下任意路径），无需额外加。

> 同批预置的还有本机前端 `account.eacm.cn`（passport 自己的 SPA）。

---

## 2. 基础信息（生产环境）

| 项 | 值 |
|---|---|
| 认证基址 (base URL) | `https://passport.eacm.cn` |
| 算法 | `RS256`（非对称；项目1 用**公钥**验签，**无需共享密钥**） |
| 访问令牌 TTL | 30 分钟 |
| 刷新令牌 TTL | 14 天 |
| issuer (`iss`) | `lotus-passport`（建议校验） |

> 本地联调时 passport 跑 `http://localhost:8000`（dev 模式自动放开 `localhost` CORS），
> 项目1 前端 `http://localhost:3000`。生产一律走上面的 HTTPS 基址。

---

## 3. 关键端点

| 用途 | 方法 + 路径 |
|---|---|
| 认证元信息（一键引导 SDK） | `GET /.well-known/passport-configuration` |
| 公钥 (JWKS) | `GET /.well-known/jwks.json`（另提供 `GET /api/v1/.well-known/jwks.json`） |
| 用户态 | `GET /api/v1/userinfo/` |
| 刷新令牌 | `POST /api/v1/token/refresh/` |
| 第三方登录入口 | `GET /api/v1/oauth/{provider}/login/` |
| 回调 | `GET /api/v1/oauth/{provider}/callback/`（QQ 另接受无尾斜杠形式） |
| 登出（真实登出，吊销 jti） | `POST /api/v1/logout/` |
| 健康检查 | `GET /api/v1/health/` |

`{provider}` ∈ `github` / `qq` / `wechat`（微信暂未启用，passport 侧留空）。

---

## 4. 令牌（JWT）结构

- **Header**：`alg: RS256`，`kid: <密钥ID>`（项目1 用 `kid` 去 JWKS 取对应公钥验签）
- **Claims**（项目1 重点关注）：
  - `passport_user_id` —— **统一身份主键**，项目1 用它在本系统建立/关联用户
  - `user_id` —— 同 `passport_user_id`（兼容字段）
  - `email`、`nickname`
  - `exp`、`iat`、`jti`、`iss`
- **RS256 公钥轮换**：JWKS 在轮换重叠期会返回多把公钥（active + 上一把），
  项目1 按 `kid` 匹配即可，无需停机。

### 项目1 应保留的本地文件 / 配置

1. **基址常量**：项目1 本地配置里存 `PASSPORT_BASE_URL=https://passport.eacm.cn`
   （或等价的常量/环境变量），不要硬编码到业务代码。
2. **JWKS 缓存**：首次从 `https://passport.eacm.cn/.well-known/jwks.json` 拉取公钥，
   按 `kid` 索引缓存并定期刷新；**不要**把公钥写死进代码（passport 换届/轮换会失效）。
3. **回调地址**：项目1 的 OAuth 回跳填 `https://rank.eacm.cn/<你的路径>`（已在白名单）。
4. **登录跳转**：把用户引到
   `https://passport.eacm.cn/api/v1/oauth/{provider}/login/`，
   passport 完成第三方登录后跳回你的回调；你用返回结果中的 JWT 继续（或调 `/api/v1/userinfo/` 取资料）。

---

## 5. 登录流程（概览）

```
项目1 前端 ──(跳转)──> passport /api/v1/oauth/{provider}/login/
passport    ──(302)──> 第三方 (GitHub/QQ) 授权页
第三方      ──(回调)──> passport /api/v1/oauth/{provider}/callback/
passport    ──(302)──> 项目1 回调 (rank.eacm.cn/...) 带 code/state
项目1       ──(用 JWT / userinfo)──> 建立本地会话
```

---

## 6. 注意事项

- **Passkey / WebAuthn 的 RP ID 是 `passport.eacm.cn`**，由 passport 自身处理；
  项目1 若不做自有 passkey，无需关心此项。
- **微信 OAuth 暂未启用**（passport 侧 `WECHAT_CLIENT_ID/SECRET` 留空）。
  项目1 若需微信登录，等 passport 配好微信后直接用，白名单无需改。
- 改 passport 的 CORS / OAuth 白名单、密钥、端点才需联系 passport 维护者；
  项目1 只消费上述契约。
- 令牌吊销：用户主动登出会进 passport 的 Redis 黑名单；但**离线验签**（项目1 用 JWKS）
  只在令牌自然过期（≤30 分钟）后失效。高安全场景请缩短本地会话有效期或调 `/api/v1/userinfo/` 复核。

---

## 7. 联调自检清单

- [ ] 项目1 配置 `PASSPORT_BASE_URL=https://passport.eacm.cn`
- [ ] JWKS 能从 `/.well-known/jwks.json` 拉到且含 `kid`
- [ ] 用 `kid` 对应的公钥成功验签一个样例 JWT
- [ ] `rank.eacm.cn` 前端能被 CORS 放行（预检请求 200）
- [ ] 走一遍 `github`/`qq` 登录 → 回跳项目1 → 拿到 `passport_user_id`
- [ ] 登出后旧 JWT 在 passport 侧失效（如需严格校验）

---

## 8. SDK 用法（推荐：免手写 RS256 验签）

项目 1 直接用官方 SDK 离线校验 JWT，SDK 已处理算法混淆（`alg:none` / `HS256`）、`kid` 轮换、
`iss` 钉死（`lotus-passport`）、Passport 宕机降级（返回 **503** 而非误登出全员掉线）。

### Python — `lotus-passport-sdk`

```bash
pip install "lotus-passport-sdk[fastapi]"   # 按项目1后端框架选 extra: fastapi / drf / flask
```

```python
from fastapi import Depends
from lotus_passport import PassportClient
from lotus_passport.integrations.fastapi import PassportAuth

passport = PassportClient("https://passport.eacm.cn")  # 进程内单例，持有 JWKS 缓存
require_user = PassportAuth(passport)

@app.get("/me")
def me(identity = Depends(require_user)):
    return {"id": identity.passport_user_id}   # UUID，稳定关联键，落本地用户表建唯一索引
# 坏令牌 -> 401；Passport 不可达 -> 503（带 WWW-Authenticate: Bearer 质询）
```

首次见到某 `passport_user_id` 时，用 `passport.get_userinfo(token)` 补一次
`/api/v1/userinfo/` 拿头像 / 绑定方式。DRF / Flask 用法见 `lotus-passport-sdk/README.md`。

### Node / Next.js — `lotus-passport`

```bash
npm install lotus-passport
```

```ts
// app/api/me/route.ts（App Router，Edge 安全，纯 WebCrypto）
import { createPassportClient, requireIdentity, toErrorResponse } from 'lotus-passport/next';
const passport = createPassportClient('https://passport.eacm.cn');

export async function GET(req: Request) {
  try {
    const identity = await requireIdentity(passport, req);
    return Response.json({ passportUserId: identity.passportUserId });
  } catch (err) {
    return toErrorResponse(err); // 401 坏令牌 / 503 Passport 宕机
  }
}
```

Express 用法见 `lotus-passport-sdk-js/README.md`。两个 SDK 均为零硬依赖、离线验签、对称算法拒绝。
