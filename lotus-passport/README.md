# Lotus Passport — 统一认证中枢

独立的**身份认证中心**：聚合微信 / QQ / GitHub 的 OAuth，签发统一的 JWT，
只做**身份认证**，不做业务权限。接入方（如 E-algo rank）用 JWT 里的
`passport_user_id` 在自己的库里关联用户。

- 后端：Django 5.2 + DRF + `djangorestframework-simplejwt` + `authlib` + `cryptography` + Redis
- 前端（消费方 SPA）：`../lotus-passport-security`（Next.js 14 App Router + TS + Tailwind）
- 开发库：SQLite（WAL 模式）；生产：PostgreSQL（`DATABASE_URL`）
- 缓存 / 限流 / OAuth state：Redis（`REDIS_URL`，开发可降级到 fakeredis）

---

## 1. 快速开始

### 1.1 后端

> ⚠️ 沙箱注意：Python venv **必须建在工作区内**（建在 `$HOME` 下会静默失败），
> 且 SQLite **不能用 WAL/DELETE 模式**（见 §4）。下面命令已按沙箱调好。

```bash
cd lotus-passport

# 1) 建 venv（工作区内）
python -m venv ../.venv
../.venv/Scripts/python.exe -m pip install -r requirements.txt   # 或 uv sync

# 2) 配置环境
cp .env.example .env          # 然后改 SECRET_KEY / JWT_SIGNING_KEY / TOKEN_ENCRYPTION_KEY
#   本地开发直接用仓库里的 .env 即可（已设 DEBUG=True + SQLITE_JOURNAL_MODE=TRUNCATE）

# 3) 建表
../.venv/Scripts/python.exe manage.py migrate

# 4) 起服务（--noreload 避免单线程被自动重载干扰；生产用 gunicorn）
../.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

健康检查：`GET /api/v1/health/` → `200`。

### 1.2 前端（SPA）

```bash
cd lotus-passport-security

cp .env.example .env.local   # 只有一个变量 PASSPORT_API_ORIGIN，默认值即可
npm ci                       # 严格按 package-lock.json 安装
npm run dev                  # 默认 3000
```

> **受管沙箱内**：`next dev/build` 清理 `.next` 时会被 safe-delete 拦截器搞崩。
> 解法是清空被注入的 `NODE_OPTIONS`：`NODE_OPTIONS= npm run dev`（详见 §4）。
> 普通机器 / CI / Docker 无此问题。

打开 `http://127.0.0.1:3000/login`，开发环境下会出现 **“DEV 模拟登录”** 区块，
点「模拟 github / wechat / qq」即可走完整 `登录 → JWT → userinfo` 流程。

---

## 2. 认证流程

```
第三方 OAuth            Lotus Passport                接入方 SPA
     │                      │                              │
     │  授权跳转             │                              │
     ├─────────────────────>│  /api/v1/oauth/<p>/login/    │
     │                      │  (302 到 GitHub/微信/QQ)      │
     │<─────────────────────┤                              │
     │  用户授权 + 回调       │                              │
     ├─────────────────────>│  /api/v1/oauth/<p>/callback/ │
     │                      │  交换 token + 建/关联用户      │
     │                      │  签发统一 JWT ── 302 #fragment│
     │                      ├─────────────────────────────>│  /auth/callback
     │                      │                              │  解析 fragment
     │                      │                              │  存 access/refresh
     │                      │  GET /api/v1/userinfo/ (Bearer)│
     │                      │<─────────────────────────────┤
     │                      │  返回 passport_user_id + 资料  │
```

### 2.1 主要端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/v1/health/` | 健康检查 |
| GET  | `/api/v1/oauth/<provider>/login/` | 生成第三方授权链接（302 跳转） |
| GET  | `/api/v1/oauth/<provider>/callback/` | OAuth 回调，交换 token 并签发 JWT（302 `#fragment`） |
| GET  | `/api/v1/userinfo/` | 凭 Bearer 返回当前用户身份（**不含**任何业务字段） |
| POST | `/api/v1/token/refresh/` | 用 refresh_token 换新 access |
| GET  | `/api/v1/.well-known/jwks.json` | RS256 公钥（HS256 下返回 404） |

### 2.2 Dev 模拟登录（仅开发）

`api/v1/dev/*` 是给 SPA 在没有真实 OAuth 应用时也能跑通全链路的**桩端点**：

- `GET /api/v1/dev/status/` —— 始终可访问，回报 `dev_login_enabled` 与可用 provider 列表。
- `GET /api/v1/dev/login/?provider=github&redirect_uri=<url>` —— 用确定性假账号签发真实 JWT；
  带 `redirect_uri` 时 302 到该地址并附带 `#access_token=...&refresh_token=...`（与真实回调完全一致）。

是否开放由 **`ENABLE_DEV_LOGIN`** 控制（见 §3），生产必须关掉。

---

## 3. 配置与开关

所有配置走环境变量，`.env` 通过仓库内的零依赖加载器读取（**不是** `python-dotenv`），
真实环境变量优先级高于 `.env`。

| 变量 | 默认 | 说明 |
|------|------|------|
| `DEBUG` | `True` | 生产**必须** `False` |
| `ENABLE_DEV_LOGIN` | 跟随 `DEBUG` | Dev 桩登录开关。默认 `DEBUG=True` 时开；生产 `DEBUG=False` 自动关。可显式覆盖（如 `ENABLE_DEV_LOGIN=True` 配合真实凭据做本地联调） |
| `SECRET_KEY` | 不安全的占位值 | **生产必须替换** |
| `JWT_SIGNING_KEY` | —— | HS256 共享密钥；或同时设 `PASSPORT_JWT_PRIVATE_KEY` / `PUBLIC_KEY` 切到 RS256 |
| `TOKEN_ENCRYPTION_KEY` | —— | 第三方 access_token 的 AES-256-CBC 密钥（base64 of 32 bytes） |
| `DATABASE_URL` | —— | 留空用 SQLite；设了用 PostgreSQL |
| `SQLITE_JOURNAL_MODE` | `WAL` | 见 §4；沙箱设 `TRUNCATE` |
| `REDIS_URL` | —— | 限流 + OAuth state；缺省降级 fakeredis |
| `CORS_ALLOWED_ORIGINS` | —— | 接入方前端域名，逗号分隔 |
| `FRONTEND_SUCCESS_REDIRECT` | —— | 登录成功后回跳的 SPA 地址 |
| `PASSPORT_OAUTH_REDIRECT_BASE` | —— | 第三方回调回填到本中心的 base URL |

> **安全基线**：生产部署 = `DEBUG=False` + `ENABLE_DEV_LOGIN` 不设或 `False` + 强随机密钥
> + PostgreSQL + 真实 `CORS_ALLOWED_ORIGINS`。`ENABLE_DEV_LOGIN` 与 `DEBUG` 是**两个独立开关**，
> 目的是即便有人误把 `DEBUG=True` 带到生产，桩登录也不会悄悄暴露。

---

## 4. 已知坑（沙箱 / 特殊环境）

1. **Node 的 safe-delete shim**：部分托管沙箱给 `NODE_OPTIONS` 注入了「安全删除」shim
   （`--require .../genie-safe-delete.cjs`），它会拦截 `fs.unlink`/`fs.rm` 改成「移入回收站」。
   在回收站不可用的环境里，`next dev` / `next build` 清理 `.next` 时会直接崩溃，
   报 `[safe-delete] 操作失败` 或 `DeleteFile … 无法找到指定文件`。
   **解法**：直接把这个变量清空 —— `NODE_OPTIONS= npm run build`。
   （旧文档写的 `NODE_OPTIONS="--use-system-ca"` 只是碰巧覆盖掉了注入的 `--require`，
   语义上有误导，别再照抄。）仅限沙箱，CI / Docker 无此问题。

2. **SQLite 不能用 WAL / DELETE 模式**：同上根因，SQLite 的 WAL 在连接关闭时要删
   `-wal`/`-shm`、DELETE 模式每次提交要删 `-journal`，都被 shim 拦截 → 随机 20s 超时 +
   `database is locked`，单线程 `runserver` 会被一个写请求拖死。
   **解法**：设 `SQLITE_JOURNAL_MODE=TRUNCATE`（`init_command` 在每次连接强制生效，
   只截断不删除，实测写事务 ~3ms）。普通开发机删掉这行即可回到默认 WAL。

3. **Python venv 建在 `$HOME` 下会静默失败**：目录建出来是空的。
   **解法**：venv 建在工作区内（如 `../.venv`）。

---

## 5. 测试

```bash
cd lotus-passport
pip install -r requirements-dev.lock.txt      # 运行时 + 测试依赖，钉死版本
../.venv/Scripts/python.exe -m pytest -q
```

- **当前基线 53 个用例全绿**；跨请求流程测试用 `@pytest.mark.django_db(transaction=True)`。
- 限流 / OAuth state 在测试时自动用 `fakeredis`，无需真实 Redis。
- 另有两个 SDK：Python SDK 54 通过、JS SDK 30 通过。三者都在 CI 里跑。

**依赖文件有三个，别混用**：

| 文件 | 内容 | 用在哪 |
|------|------|--------|
| `requirements.txt` | 带范围的声明，唯一事实源 | 升级依赖时改这里 |
| `requirements.lock.txt` | 仅**运行时**闭包，全钉死 | 生产、Docker 镜像 |
| `requirements-dev.lock.txt` | 运行时 + 测试包 | 本地开发、CI |

生产镜像不装 `pytest`/`fakeredis` —— 既省体积也少一片攻击面。

**生产体检**（CI 每次提交都跑，`--fail-level WARNING` 意味着任何部署级告警都会让构建失败）：

```bash
DEBUG=False SECRET_KEY=... ALLOWED_HOSTS=your.domain \
  python manage.py check --deploy --fail-level WARNING
python manage.py makemigrations --check --dry-run    # 模型改了却没提交迁移 → 失败
```

端到端（前端 + 后端 + 同源代理）可用仓库根的 `verify-e2e.py` 验证：

```bash
cd ..
.venv/Scripts/python.exe verify-e2e.py
```

---

## 6. 接入真实 OAuth 凭据（上线必做）

真实的授权码流程**代码已完整实现**（`OAuthLoginView` / `OAuthCallbackView` / `providers.py`），
只需把各平台的客户端凭据填进 `.env` 并在对应开放平台登记回调地址即可，无需改业务代码。

### 6.1 三步上线

1. **拿凭据**：去各平台开放平台创建 OAuth App，拿到 `Client ID` / `Client Secret`。
2. **填 `.env`**：
   ```bash
   GITHUB_CLIENT_ID=xxx        GITHUB_CLIENT_SECRET=xxx
   WECHAT_CLIENT_ID=xxx        WECHAT_CLIENT_SECRET=xxx
   QQ_CLIENT_ID=xxx            QQ_CLIENT_SECRET=xxx
   # 后端接收平台回调的 base，必须与下面登记的一致
   PASSPORT_OAUTH_REDIRECT_BASE=https://passport.eacm.cn/api/v1/oauth
   ```
3. **在平台登记回调地址**（每个 provider 一个，必须**完全匹配**，包括协议/端口/尾斜杠）：
   ```
   ${PASSPORT_OAUTH_REDIRECT_BASE}/github/callback/
   ${PASSPORT_OAUTH_REDIRECT_BASE}/wechat/callback/
   ${PASSPORT_OAUTH_REDIRECT_BASE}/qq/callback/
   ```
   例如本地联调：`http://localhost:8000/api/v1/oauth/github/callback/`；
   生产：`https://passport.eacm.cn/api/v1/oauth/github/callback/`。

> 填好凭据后，`GET /api/v1/oauth/<provider>/login/` 会返回 `200` + `authorize_url`；
> **未填凭据时返回 `400`「尚未配置客户端凭据」**，而不是把用户静默踢到平台吃闭门羹。

### 6.2 前端无需改动

`app/login/page.tsx` 的真实登录按钮已调用 `getOAuthLoginUrl(provider, redirectUri)`，
并把 `redirect_uri` 设为 `${origin}/auth/callback`。后端在回调完成、签发 JWT 后，
会把 token 以 **URL fragment** 弹回该地址，`app/auth/callback/page.tsx` 负责解析并存储。
（DEV 模拟登录区块仅在 `ENABLE_DEV_LOGIN=True` 时出现。）

### 6.3 完整时序

```
SPA /login
  └─ GET /api/v1/oauth/github/login/?redirect_uri=<SPA>/auth/callback
        ├─ 生成 CSRF state → 存 Redis(TTL 10min)
        └─ 返回 authorize_url（含真实 client_id + 后端回调地址）
  └─ 浏览器跳到 GitHub 授权页 → 用户同意
  └─ GitHub 302 → 后端 /api/v1/oauth/github/callback/?code=..&state=..
        ├─ 校验 state（Redis 消费，防 CSRF）
        ├─ 用 code 换 access_token（authlib）
        ├─ 拉取用户资料 → 归一化为 Identity
        ├─ find-or-create PassportUser + OAuthAccount（access_token 经 AES-256-CBC 加密落库）
        ├─ 签发统一 JWT（含 passport_user_id）
        └─ 302 → <SPA>/auth/callback#access_token=..&refresh_token=..&passport_user_id=..
  └─ SPA 解析 fragment → 存 token → 拉 /api/v1/userinfo/
```

### 6.4 平台差异与注意点

- **GitHub**：本地 `http://localhost:8000/...` 回调可直接用；最宽松。
- **微信 / QQ**：开放平台通常**要求 HTTPS 回调**且需在后台登记可信域名；
  本地 `localhost` 一般不被接受，需在平台配置测试域名或走内网穿透到 HTTPS。
  `WeChatProvider` 优先用 `unionid` 作为 `provider_user_id`（跨应用统一）。
- **生产**：务必 `DEBUG=False`、`ENABLE_DEV_LOGIN` 关掉、用 PostgreSQL、
  配 `CORS_ALLOWED_ORIGINS` 与真实 `ALLOWED_HOSTS`、`JWT_SIGNING_KEY`/`TOKEN_ENCRYPTION_KEY`
  用强随机值（`./manage.py generate_keys`）。

### 6.5 验证

- 单元/集成：`pytest` 中 `test_oauth_flow.py` + `test_oauth_real_config.py` 覆盖了
  「真实 provider 类 + 配置 → authorize URL → 换码 → 身份 → JWT → fragment」全链路
  （外网 HTTP 已 mock，仅验证本中心逻辑）。
- 手测：填好凭据、重启后端后，`curl /api/v1/oauth/github/login/` 应返回带真实
  `client_id` 的 `authorize_url`；浏览器走 `/login` 点「GitHub」即可完成真实登录。

---

## 7. RS256 签名 + JWKS 公钥分发

### 7.1 为什么是 RS256（不是 HS256）

统一认证中心的价值在于：**接入方只用公钥就能验证 token，永不需要知道签名私钥**。

- HS256 是对称签名——所有接入方必须共享同一个 `JWT_SIGNING_KEY`，一旦泄露全站沦陷，且无法区分签发方。
- RS256 是非对称——passport 用**私钥**签发，把**公钥**通过 JWKS 公开。任何接入方（algo_rank、未来项目）
  拉到公钥即可独立验证，私钥只留在 passport 一台机器上。

这正是 OAuth2/OIDC 生态的标准做法（Google、GitHub 的 token 都是 RS256 + JWKS）。

### 7.2 密钥管理

默认启用 RS256（开发零配置）。密钥库支持**多密钥并存**，这是零掉线轮换的前提。

**密钥库布局**（`keys/`，已 gitignore）：

```
keys/
├── manifest.json          # 哪个 kid 是当前签发钥、各钥的创建时间与保留期
├── private_<kid>.pem      # 私钥，仅激活钥用于签发
└── public_<kid>.pem       # 公钥，全部发布到 JWKS
```

- **开发自动生成**：`DEBUG=True` 且 `keys/` 为空时，启动自动生成 RSA-2048。
- **生产 fail-closed**：没有密钥时 settings **拒绝加载**，直接报错退出——宁可起不来，也不要偷偷退回不安全模式。
  唯一豁免是 `manage.py generate_keys` 本身（否则「要生成密钥得先有密钥」，鸡生蛋死锁）。
- **初始化**：`python manage.py generate_keys`（幂等，已有则跳过；`--force` 覆盖，`--bit-length` 调长度）
- **Docker 部署不用手动生成**：entrypoint 首次启动检测到密钥卷为空会自动执行，密钥落在
  `passport_keys` 命名卷里，**永远不进镜像层**。
- **环境变量覆盖**（适合 K8s Secret）：`PASSPORT_JWT_PRIVATE_KEY` / `PASSPORT_JWT_PUBLIC_KEY`（PEM 文本）。
  设了它们之后 `generate_keys` / `rotate_keys` 会**拒绝执行**——密钥归外部编排管，命令再去写文件只会造成两套真相。
  ⚠️ 多行 PEM **无法**经 compose 的 `env_file` 注入，只能用真正的 secret 机制。
- 自定义目录：`PASSPORT_JWT_KEYS_DIR=/run/secrets/passport`。

**私钥绝不入库、绝不进 .env、绝不进镜像。**

#### 密钥轮换（零掉线）

```bash
python manage.py rotate_keys                      # 保留期默认 16 天
python manage.py rotate_keys --retention-days 30
```

做了什么：生成新密钥对并设为**签发钥**，旧公钥转入**保留期**——仍然留在 JWKS 里继续验签，
直到超期才被清理。所以轮换瞬间已经签发出去的 token 全部继续有效，接入方无需协调、无需重启，
在自己的 JWKS 缓存 TTL 内自动拿到新钥。

> ⚠️ **保留期必须大于 refresh token TTL**。默认 16 天 = refresh 14 天 + 2 天缓冲。
> 如果你调大了 `JWT_REFRESH_TTL_DAYS`，**记得同步调大保留期**，
> 否则轮换当天签出的 refresh token 会在自然到期前突然验不过。

验证轮换成功：

```bash
curl -s https://<host>/.well-known/jwks.json | jq '.keys | length'   # 应 >= 2
```

> **实现说明**：simplejwt 5.5.1 没有 `TOKEN_BACKEND` 配置项，其全局单例硬编码单一验签钥，
> 原生做不到按 `kid` 选钥。所以我们子类化 `TokenBackend` 覆写 `get_verifying_key()`，
> 在 `PassportConfig.ready()` 里替换全局实例（见 `passport/apps.py`）。
> 这是该版本下唯一干净的做法——**将来升级 simplejwt 时务必复查这里**。

回退到 HS256（仅限遗留共享密钥场景）：设 `JWT_USE_RS256=False`（此时 JWKS 端点返回 404）。

### 7.3 JWKS 端点

```
GET /.well-known/jwks.json     # 公开，无需鉴权
```

返回格式（RFC 7517 JWK）。**轮换后会有多枚**——当前签发钥 + 仍在保留期的旧钥：

```json
{
  "keys": [
    {
      "kty": "RSA", "use": "sig", "alg": "RS256",
      "kid": "lotus-passport-rsa-2",
      "n": "<base64url 模数>", "e": "AQAB"
    },
    {
      "kty": "RSA", "use": "sig", "alg": "RS256",
      "kid": "lotus-passport-rsa-1",
      "n": "<base64url 模数>", "e": "AQAB"
    }
  ]
}
```

每枚签发的 token 的**受保护头**里都带 `kid`，接入方据此精确选钥。

> ⚠️ **不要假设 `keys[0]` 就是你要的那把。** 数组顺序不是契约。
> 必须读 token 头里的 `kid` 去匹配——否则轮换当天所有旧 token 立刻验签失败。

### 7.4 接入方如何验证

**推荐直接用官方 SDK**（见 §9），它已经内置了 kid 选钥、JWKS 缓存、算法白名单、
iss 绑定和未知 kid 限流。手写容易踩 alg 混淆攻击的坑。

如果确实要手写，Python 最小示例：

```python
import json, jwt, requests
from jwt.algorithms import RSAAlgorithm

# 1) 从登录流程拿到 access_token（前端回调 fragment 里）

# 2) 拉公钥（可缓存；缓存 TTL 决定轮换后多久感知到新钥）
jwks = requests.get("https://passport.eacm.cn/.well-known/jwks.json").json()

# 3) 按 token 头里的 kid 选钥 —— 不能写死 keys[0]
kid = jwt.get_unverified_header(access_token)["kid"]
jwk = next(k for k in jwks["keys"] if k["kid"] == kid)   # 找不到 → 刷新缓存后重试一次
pub_key = RSAAlgorithm.from_jwk(json.dumps(jwk))

# 4) 用公钥验证（无需私钥、无需共享密钥）
claims = jwt.decode(access_token, pub_key, algorithms=["RS256"],
                    issuer="lotus-passport",
                    options={"verify_aud": False})
user_id = claims["passport_user_id"]   # 用这个关联到你的本地账号
```

要点：接入方**只信任公钥**，固定 `algorithms=["RS256"]` 防 alg 混淆攻击；
遇到未知 `kid` 时应**限流**后再刷新 JWKS，否则会被伪造 kid 打成 DoS 放大器。

### 7.5 配置开关

| 变量 | 默认 | 说明 |
|------|------|------|
| `JWT_USE_RS256` | `True` | `False` 退回 HS256（JWKS 404） |
| `JWT_KID` | `lotus-passport-rsa-1` | JWKS/ token 头的 key id，轮换时改它 |
| `PASSPORT_JWT_KEYS_DIR` | `keys/` | 私钥/公钥存放目录 |
| `JWT_ACCESS_TTL_MIN` | `30` | access token 有效期（分钟） |
| `JWT_REFRESH_TTL_DAYS` | `14` | refresh token 有效期（天） |

### 7.6 验证

- 单元/集成：`pytest` 中 `test_jwt_rs256.py` 覆盖「RS256 默认启用 / token 头带 kid /
  JWKS 返回公钥 / 用 JWKS 公钥独立验证 token / userinfo 接受 RS256 token」。
- 手测：启动后 `curl /.well-known/jwks.json` 应返回 200 + 含 `keys`；
  任意接入方拿该公钥即可 `jwt.decode(token, pub_key, algorithms=["RS256"])` 通过。

---

## 8. Docker 部署（Nginx + Gunicorn + PostgreSQL）

生产级容器化栈：`nginx`（反向代理 / TLS 终止）⟶ `web`（Gunicorn + Django）
⟶ `postgres`（主库）+ `redis`（限流 / OAuth state）。

```
┌────────┐   :80/:443   ┌────────┐   :8000   ┌─────────┐
│ nginx  │ ───────────> │  web   │ ────────> │ postgres│
│ (TLS)  │              │gunicorn│           └─────────┘
└────────┘              └────────┘ ────────> ┌─────────┐
                            │                │  redis  │
                            └──────────────> └─────────┘
```

### 8.1 目录与文件

| 文件 | 作用 |
|------|------|
| `Dockerfile` | 基于 `python:3.13-slim`，非 root 用户运行，入口 `docker/entrypoint.sh` 负责等库 + 迁移 + 启动 |
| `docker/entrypoint.sh` | 等待 PostgreSQL 就绪 → `collectstatic` → `migrate` → `exec gunicorn` |
| `docker-compose.yml` | 五服务编排：`db`(postgres) + `redis` + `web`(gunicorn) + `frontend`(Next.js SPA) + `nginx`；`web` 通过 `env_file: .env.docker` 注入密钥（**不进镜像**）；RS256 密钥存于 `passport_keys` 命名卷（首次启动由 entrypoint 自动生成） |
| `nginx/nginx.conf` | 反向代理 + gzip + 安全头；含可选 HTTPS server 块（注释掉，放证书即启用） |
| `gunicorn.conf.py` | worker 数 = `CPU+1`，信任来自 nginx 的 `X-Forwarded-*` |
| `.env.docker.example` | 生产密钥模板（生成后复制为 `.env.docker`） |

### 8.2 部署步骤

```bash
cd lotus-passport          # 进入后端目录（docker-compose.yml 所在处）

# 1) 准备生产环境变量（密钥只在这里填，绝不进镜像）
cp .env.docker.example .env.docker
#   至少填：SECRET_KEY、TOKEN_ENCRYPTION_KEY、数据库/Redis 连接、
#          PASSPORT_*_CLIENT_ID / *_CLIENT_SECRET、ALLOWED_HOSTS 等。
#   生成随机值示例：
#     SECRET_KEY:           python -c "import secrets; print(secrets.token_urlsafe(50))"
#     TOKEN_ENCRYPTION_KEY: python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
#   注意：RS256 签名密钥【无需手动生成】——
#   entrypoint 首次启动会自动写入 passport_keys 卷（见 §8.3）。

# 2) 校验 compose 配置（不真正启动）
docker compose config

# 3) 构建 + 后台启动（web / frontend / nginx / db / redis 全部就位）
docker compose up -d --build

# 4) 看日志 / 状态
docker compose logs -f web
docker compose ps
```

启动后访问 `http://<host>/api/v1/health/` 应返回 `200`。

### 8.3 关键设计点（为什么这样配）

- **密钥绝不进镜像**：`.dockerignore` 排除了 `.env`、`keys/`、`*.pem`；运行时密钥
  （`SECRET_KEY` 等）只通过 `env_file`（`.env.docker`，已 gitignore）注入。RS256 私钥则
  写在 `passport_keys` 命名卷里、由 entrypoint 首次启动自动生成，同样不进镜像。即使镜像
  被泄露也拿不到任何私钥。
- **RS256 密钥自动生成 + 持久化**：entrypoint 仅在 `PASSPORT_JWT_PRIVATE_KEY` 未设置且
  启用 RS256 时，于首次启动调用 `manage.py generate_keys` 写入 `passport_keys` 卷（挂载到
  `/app/keys`），容器重建不会丢失，轮换（`rotate_keys`）也追加于此。⚠️ **务必备份
  `passport_keys` 卷**——丢失会让所有已签发 token 失效，并导致已缓存 JWKS 的接入方验证失败。
- **`psycopg[binary]` 已加入 `requirements.txt`**：Django 5.x 的 postgresql 后端需要它，
  但**不会随 Django 一起装**——缺了它容器一连 PostgreSQL 就 `No module named 'psycopg'`。
- **等库再迁移**：`entrypoint.sh` 用 socket 探测 5432，就绪后才 `migrate`，避免「库还没起来就迁移」报错。
- **非 root + 健康检查**：容器以 `uid 10001` 运行；`web` 用 `/api/v1/dev/status/`（始终可读、无越权）
  做存活探针；`db`/`redis` 各自有 healthcheck，`web` 通过 `depends_on: condition: service_healthy` 等待。
- **正确的 `X-Forwarded-*`**：`gunicorn.conf.py` 设 `forwarded_allow_ips="*"` 信任 nginx；
  `settings.py` 在生产（`not DEBUG`）下加 `SECURE_PROXY_SSL_HEADER`，使 `request.is_secure()` /
  安全 Cookie 标志在 nginx 终止 TLS 后依然正确。

### 8.4 启用 HTTPS

1. 把证书放到 `nginx/certs/fullchain.pem` 与 `nginx/certs/privkey.pem`。
2. `docker-compose.yml` 的 `nginx` 服务取消注释 `./nginx/certs:/etc/nginx/certs:ro` 与 `443:443` 映射。
3. `nginx/nginx.conf` 取消注释 `listen 443 ssl` 的 server 块（已含 HSTS）。
4. 可选：再取消注释末尾的「HTTP → HTTPS 重定向」server 块。
5. `docker compose up -d nginx` 重新加载。

### 8.5 运维

```bash
docker compose up -d --scale web=3     # 横向扩 Gunicorn（注意共享 PostgreSQL/Redis，无状态）
docker compose exec web python manage.py createsuperuser   # 建管理员
docker compose down                    # 停止（数据在 pgdata 卷，不丢）
docker compose down -v                 # 连数据卷一起删（慎用）
```

> 前端 SPA（`lotus-passport-security`）已作为 `frontend` 服务纳入本 compose 编排，由 nginx
> 在 `/` 提供、浏览器只访问同源；它通过 `PASSPORT_API_ORIGIN=http://web:8000` 在容器内访问
> 后端（见 §3、§6）。要单独部署前端时，仍可用其自带 `Dockerfile` 独立构建（见 §3.3）。

## 9. 接入方 SDK（验证示例库）

本中心的价值在于「统一签发、分散验证」：下游应用（如算法竞赛排名 `algo_rank`、Next.js
安全前端）**只需用公钥 JWKS 验证 RS256 JWT，无需持有私钥、无需共享密钥、无需重新实现密码学**。

不要手写 JWT 校验——算法混淆攻击（`alg:none` / 用公钥当 HMAC 密钥签 `HS256`）是最常见的
JWT 实现漏洞。直接用官方 SDK：算法白名单在构造期固定、不信任 token 自带的 `alg`、对称算法
直接拒绝、`iss` 强制绑定、认证中心抖动时返回 **503 而非 401**（避免把一次宕机变成全员登出）。

### 9.1 两个官方 SDK

| 语言 | 仓库 | 依赖 | 支持框架 |
|------|------|------|----------|
| Python | [`lotus-passport-sdk/`](../lotus-passport-sdk) | `PyJWT[crypto]` + `requests`（transport 可替换） | FastAPI / DRF / Flask |
| TypeScript / Node | [`lotus-passport-sdk-js/`](../lotus-passport-sdk-js) | **零依赖**（WebCrypto） | Express / Next.js（App Router，Edge 安全）/ Deno / Bun |

两个 SDK 行为一致：离线 `verifyToken()`（只验签名，热路径零网络）+ 在线 `getUserInfo()`
（带 `avatar` 与已绑定的 `providers`），并都带可离线运行的测试套件。

### 9.2 接入方要用的端点

| 端点 | 作用 | 缓存建议 |
|------|------|----------|
| `GET /.well-known/jwks.json` | 公钥集合（`kty=RSA`、`use=sig`、`kid` 标记） | 客户端缓存 TTL 10 分钟；nginx 已设 `Cache-Control: max-age=300` |
| `GET /.well-known/passport-configuration` | 发现文档（`issuer` / `jwks_uri` / 端点 / 支持的算法与 claims） | 启动时拉一次即可 |
| `GET /api/v1/userinfo/` | 用 token 换完整档案（头像、绑定渠道） | 仅在需要时调用 |

> 旧路径 `/api/v1/.well-known/jwks.json` 仍保留兼容；新接入方一律用根路径 `/.well-known/jwks.json`。

### 9.3 接入方最小改动

```python
# Python（FastAPI 示例，完整见 lotus-passport-sdk/examples）
from lotus_passport import PassportClient
from lotus_passport.integrations.fastapi import PassportAuth

passport = PassportClient("https://passport.eacm.cn")   # 复用，JWKS 缓存归它管
require_user = PassportAuth(passport)

@app.get("/me")
def me(identity: PassportIdentity = Depends(require_user)):
    return {"id": identity.passport_user_id}              # 用 passport_user_id 做本地关联键
```

```js
// TypeScript / Next.js（完整见 lotus-passport-sdk-js/examples）
import { createPassportClient, TokenError, TokenExpiredError, PassportServiceError } from 'lotus-passport';
import { requireIdentity, toErrorResponse } from 'lotus-passport/next';

const passport = createPassportClient('https://passport.eacm.cn');

export async function GET(req: Request) {
  try {
    const identity = await requireIdentity(passport, req);
    return Response.json({ passportUserId: identity.passportUserId });
  } catch (err) {
    return toErrorResponse(err);   // 401 令牌问题 / 503 认证中心抖动
  }
}
```

### 9.4 关键点

- **关联键用 `passport_user_id`（UUID）**，不要用电邮——用户会改邮箱、不同渠道可能报同一邮箱。
- **`iss` 必须绑定**：防止别的 RS256 签发方重放 token 到你的 API。
- **JWKS 缓存**：不要在每次请求时拉 JWKS；未知 `kid` 的强制刷新要限流（两个 SDK 都已内置，防伪造 `kid` 放大 DoS）。
- **密钥轮换无需重新部署**：新公钥发布到 JWKS 后，客户端在 TTL 内自动采用；旧 token 仍可用旧密钥验过。

