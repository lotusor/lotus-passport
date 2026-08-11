# Lotus Passport 上线前验证报告（PRE-LAUNCH VERIFICATION）

> 生成时间：2026-08-10
> 范围：上线前必需验证维度；标注每项状态（✅ PASS / ⚠️ ACTION / 🔒 BLOCKED-需部署后跑）
> 原则：应用当前**尚未部署到服务器**（服务器 `$PROJ` 仅有证书目录），故所有需"运行中服务"的验证列为 BLOCKED，
> 并给出部署后执行的"上线门禁"命令。代码/配置层面的验证已尽量实跑。

---

## 1. 配置项与生产环境一致性核对  ✅ PASS

| 配置项 | .env.production | 服务器实际 | 结论 |
|---|---|---|---|
| `DEBUG` | `false` | compose `DEBUG:"False"`（双保险） | ✅ |
| `DATABASE_URL` | `postgres://lotus_passport:****@127.0.0.1:5432/lotus_passport` | BT-Panel PG 角色/库 `lotus_passport`（scram） | ✅ 一致 |
| `REDIS_URL` | `redis://:****@127.0.0.1:6379/0` | BT-Panel Redis（强密码，bind 127.0.0.1） | ✅ 一致 |
| `SECRET_KEY` | 真实值 | — | ✅ 非 dev 占位 |
| `TOKEN_ENCRYPTION_KEY` | 真实值 | — | ✅ 非 dev 占位 |
| `ALLOWED_HOSTS` | `passport.eacm.cn` | compose 覆盖为 `passport.eacm.cn,localhost,127.0.0.1` | ✅ 含健康检查所需 |
| `SECURE_SSL_REDIRECT` | `true`（本轮开启） | — | ✅ |
| `ENABLE_DEV_LOGIN` | `false` | — | ✅ 开发桩登录关闭 |
| `CORS_ALLOWED_ORIGINS` | `account.eacm.cn, rank.eacm.cn` | — | ✅ 含项目1 |
| `OAUTH_ALLOWED_REDIRECT_URIS` | `account.eacm.cn, rank.eacm.cn` | — | ✅ 含项目1 |
| nginx 443 块 | 已启用 + 挂 `./nginx/certs` | 证书已部署到 `$PROJ/nginx/certs/` | ✅ |
| PG 密码加密 | scram-sha-256 | `password_encryption=scram-sha-256` | ✅ |

**⚠️ 注意**：`SECURE_HSTS_PRELOAD = True` 已开；一旦提交到 HSTS 预加载列表将无法轻易撤销，属有意设计，上线后留意。

---

## 2. 权限与安全性检查  ✅ PASS（1 项 ACTION）

实跑/静态确认：
- ✅ `DEBUG=false` → 生产加固全开：`SECURE_PROXY_SSL_HEADER` / `USE_X_FORWARDED_HOST` / `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` / HSTS
- ✅ CORS 显式来源（无 `*`）、`CORS_ALLOW_CREDENTIALS=true`
- ✅ OAuth 回调白名单（开放重定向防护 A-11）
- ✅ 限流：登录 20/60s、回调 30/60s、全局 IP 200/60s；暴力锁定 5 次/15min；并发会话上限 10
- ✅ 令牌吊销（Redis 黑名单，离线降级 OPEN）
- ✅ 第三方 access_token AES-256-CBC 加密存储
- ✅ JWT RS256 + JWKS 公钥分发；`dev/login` 受 `ENABLE_DEV_LOGIN` 守卫（生产 404），`dev/status` 仅吐配置无密钥
- ✅ Passkey/WebAuthn、hCaptcha（secret 已配）就位
- ⚠️ **ACTION**：无 Sentry/metrics 等集中监控（见 §6）

---

## 3. 功能验证 / 接口连通性  ✅ PASS（测试实跑）

- **测试套件实跑**：`.venv` + pytest 9.1.1 + Django 5.2.17，`pytest -q` → **122/122 通过**（退出码 0）
  - 覆盖：account / account_deletion / avatar / captcha / crypto / discovery / jwt / jwt_rs256 /
    keys / oauth_bind / oauth_flow / oauth_real_config / passkeys / providers / rate_limit / security / security_factors
- 路由核对：health / oauth(login/callback/bind/unbind/accounts) / userinfo / logout / token-refresh /
  profile / devices / sessions / login-history / password / passkeys / webauthn / **JWKS + passport-configuration**
- 🔒 BLOCKED：真实第三方 OAuth 回调（GitHub/QQ 真实账号）、真实 HTTPS 端到端，需部署后跑（§9 门禁）

---

## 4. 数据完整性校验  ✅ PASS（需部署后 migrate 复核）

- ✅ migrations：6 个（`passport/migrations/0001–0006`），models 在 `passport/models.py`
- ✅ RS256 密钥：`entrypoint` 首次启动生成到 `passport_keys` 卷（已在 compose 持久化）；**务必离线备份 `keys/`**
- 🔒 BLOCKED：服务器 `python manage.py migrate --check` 复核（部署后跑，§9）

---

## 5. 错误处理与异常场景  ✅ PASS（静态）

- ✅ 自定义异常处理器 `passport.exceptions.custom_exception_handler`（DRF）
- ✅ 限流返回 429（中文提示）；provider 未配置返回 400；未知 provider 400
- ✅ JWKS 在无 RS256 / 无公钥时返回 404；异常返回 500（含原因）
- ✅ `passport-configuration` 在 RS256 正常时返回完整端点地图
- ⚠️ 建议部署后人工验证：无效 JWT、过期 JWT、错误 kid、CSRF、缺失 token 的 401 表现

---

## 6. 日志与监控系统确认  ⚠️ ACTION（缺口）

- ❌ 未配置集中式日志/监控（`grep LOGGING|sentry|metrics` 无结果），依赖 Django 默认日志 → 容器 stdout
- ⚠️ 现状可用项：nginx/容器 `docker compose logs`、web 健康检查探针、`acme.sh` 自动续期 cron
- **ACTION（建议上线前或上线后尽快）**：
  1. 至少确认 `docker compose logs -f web` 能正常输出请求/错误
  2. 视需要接入 Sentry / 日志采集（Loki/ELK），并加基础告警（5xx 率、证书过期、健康检查失败）
  3. 数据库/Redis 备份：BT-Panel 已托管，确认定期备份开启

---

## 7. 性能与负载测试  🔒 BLOCKED（需部署后跑）

- 限流已配置（见 §2），具备基础抗压/防刷能力
- 🔒 部署后建议（注意全局 IP 限流 200/60s 会限制压测，压测时可临时放宽或标注意图）：
  ```bash
  # 简单健康检查压测（注意限流）
  ab -n 1000 -c 50 https://passport.eacm.cn/api/v1/health/
  # 或 wrk / hey
  ```
- 真实业务链路（OAuth 回调、userinfo）压测建议用脚本模拟，避免触发第三方速率限制

---

## 8. 项目1（e-algo rank / rank.eacm.cn）预留  ✅ 已预留

- ✅ CORS + OAuth 白名单已含 `rank.eacm.cn`（settings.py 已加"项目1 预置"注释）
- ✅ 本地参考文件已建：`docs/integration/project1-ealgo-rank.md`（基址、JWKS、端点地图、令牌结构、项目1 应保留的本地文件清单、联调清单）
- 项目1 后续开发直接读该本地文件即可接入，无需改 passport 配置

---

## 9. 上线门禁（部署到服务器后必须逐项执行并留记录）

> 顺序铁律：证书已就位 → 部署代码 → `migrate` → 起服务 → 验证。反了 nginx 起不来。

```bash
PROJ=/opt/lotus-passport/lotus-passport
cd $PROJ

# (1) 确认项目代码已在（含本轮改后的 compose/nginx.conf/.env.production），且 nginx/certs 证书在
ls nginx/certs/fullchain.pem nginx/certs/privkey.pem
docker compose config        # compose 语法校验

# (2) 起服务（entrypoint 自动: 等PG → 生成RSA密钥 → collectstatic → migrate → gunicorn）
docker compose up -d --build

# (3) 数据完整性复核
docker compose exec web python manage.py migrate --check
docker compose exec web python manage.py migrate

# (4) 健康检查（先 HTTP，再 HTTPS）
curl -I http://localhost/api/v1/health/
curl -I https://passport.eacm.cn/api/v1/health/        # 期望 200 + Strict-Transport-Security

# (5) 真实登录冒烟（GitHub 已配；QQ 审核中；微信留空）
#     浏览器走一遍 /api/v1/oauth/github/login/ → 回跳 → 拿 JWT → /api/v1/userinfo/

# (6) JWKS / 发现端点
curl -s https://passport.eacm.cn/.well-known/jwks.json | head
curl -s https://passport.eacm.cn/.well-known/passport-configuration | head

# (7) 异常场景抽检
curl -s https://passport.eacm.cn/api/v1/userinfo/      # 无 token → 401
curl -s -X POST https://passport.eacm.cn/api/v1/token/refresh/  # 无 refresh → 401

# (8) 日志确认
docker compose logs -f web --tail=50

# (9) 安全收尾
#     - 改服务器 root 密码（聊天曾明文暴露 QPKZ_(y~^qx.38d）
#     - 离线备份 keys/ 与 .env.production
#     - DNSPod Token 用后可在控制台吊销重建
```

---

## 10. 总览

| 维度 | 状态 |
|---|---|
| 配置一致性 | ✅ PASS |
| 权限/安全 | ✅ PASS（监控缺口 ACTION） |
| 功能/接口 | ✅ PASS（122 测试，真实 OAuth/HTTPS 待部署） |
| 数据完整性 | ✅ PASS（migrate 待部署复核） |
| 错误处理 | ✅ PASS |
| 日志/监控 | ⚠️ ACTION（无集中监控） |
| 性能/负载 | 🔒 BLOCKED（待部署） |
| 项目1 预留 | ✅ 已预留 + 本地参考文件 |
| 上线门禁 | 🔒 部署后执行（§9） |

**结论**：代码与配置层面验证已全部通过且有记录；**应用尚未部署**，真实运行验证（功能冒烟、HTTPS 端到端、负载、migrate 复核）须按 §9 在部署后完成，方可正式上线。
