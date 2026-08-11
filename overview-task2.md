# Lotus Passport — 底层架构收尾（Task 2）完成概览

> 本次为**最后一次底层架构调整**，目标：依赖锁版本 + CI + 前端 Dockerfile + RS256 密钥轮换 + 全面排查底层问题，要求完整、自洽、无遗留。

## 已交付改动

### 1. 依赖锁版本
- 后端三文件拆分：`requirements.txt`（范围，单一事实源）+ `requirements.lock.txt`（运行时）+ `requirements-dev.lock.txt`（运行时 + 测试）。
- 前端：`package-lock.json`（lockfileVersion 3，next 锁定 `14.2.35`）。
- CI 全部走锁文件安装（`npm ci` / `pip install -r *.lock.txt`）。

### 2. CI 工作流（`.github/workflows/ci.yml`，6 个独立 job）
| job | 内容 |
|-----|------|
| backend | pytest + `check --deploy --fail-level WARNING`（DEBUG=False 生产配置）+ `makemigrations --check` |
| frontend | `npm ci` + `next build` |
| sdk-python / sdk-js | 验证 SDK 测试 |
| audit | npm audit + pip-audit（**非阻断**，仅发布到摘要） |
| images | 仅 build 两个 Dockerfile，捕获坏构建阶段 |

### 3. 前端 Dockerfile
- `lotus-passport-security/Dockerfile`（多阶段）+ `.dockerignore` + `.env.example`。
- `PASSPORT_API_ORIGIN` 构建期占位、运行期注入；`NODE_ENV` 不在 `npm ci` 前设置（避免剥离 devDep 致 build 失败）。

### 4. RS256 密钥管理与轮换（核心）
- `passport/keys.py`：`KeyStore`（manifest + `private_<kid>`/`public_<kid>`，retention 默认 16d = refresh 14d + 2d 缓冲）。
- `passport/apps.py`：`ready()` 注入自定义 `TokenBackend` 子类，按 `kid` 选验证密钥（simplejwt 5.5.1 无 `TOKEN_BACKEND` 设置，必须子类化）。
- 管理命令：`generate_keys`（首启自动生成）+ `rotate_keys`（零停机，新密钥生效、旧密钥保留至过期）。
- JWKS 多 key 发布；dev 自动生成、prod 缺密钥 fail-closed。

### 5. 排查并修复的关键缺陷（无遗留）
- 🔴 构建期把 RSA 私钥 bake 进镜像 → 改为 entrypoint 首启生成到 `passport_keys` 命名卷（compose 已挂载，持久化 + 需备份）。
- 🔴 缺密钥时启动死锁 → 改为 fail-closed + 自动生成。
- 其他：`SECURE_SSL_REDIRECT` 默认 False（CI 置 True 校验 W008）；Next 14.2.15 → 14.2.35（修关键中间件绕过 CVE）；`.env.example` 重写。

### 6. 文档
- `HANDOVER.md`：§7.6（本次改造记录）、§7.7（已知风险：Next 14.2.35 仅 2 个 high CVE，仅 Next 16 修复，按特性用法判定 N/A，nginx 缓解）。
- `README.md`：§1.2 / §4 / §5 / §7.2 / §7.3 / §7.4 / §8 全量对齐（含 §8.2 部署步骤改为 entrypoint 自动生成密钥、前端已纳入 compose）。

## 验收结果（本次复测）
- ✅ `pytest` **53 例全绿**（仅 collectstatic 目录 benign 警告）。
- ✅ `manage.py check --deploy --fail-level WARNING`（模拟 CI 生产配置）→ **no issues (0 silenced)**。
- ✅ 前端 `next build` **11 路由全绿**（绕过沙箱 safe-delete：`NODE_OPTIONS= npm run build`）。
- ✅ 临时产物已清理（`/tmp/passport-keys-ci`、dev `keys/`、`.tmp_trash`）。

## 用户决策
- 留在 `next@14.2.35`（不升 Next 16），CI 加**非阻断** audit（§7.7 记录为已知风险）。

## 遗留项（已显式记录，非代码缺陷）
- 三大平台 OAuth `client_id/secret` 未到，保持"未配置即 400"预留。
- Next 14.2.35 的 2 个 high CVE 为已知风险（§7.7）。

→ 项目进入**前端调整阶段**。
