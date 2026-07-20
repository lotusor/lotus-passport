# EACM 通行证系统 — 安全审计报告

**审计日期:** 2026-07-20
**审计范围:**
- 项目1: `algo_rank` (算法竞赛排名系统)
- 项目2: `eacm_passport` (E时代ACM令牌通行证系统)
**审计标准:** Django Security Best Practices (python-django-web-server-security.md)

---

## 审计概要

| 严重等级 | 总数 | 已修复 | 待处理 |
|----------|------|--------|--------|
| Critical | 4 | 2 | 2 (部署配置) |
| High | 8 | 5 | 3 |
| Medium | 10 | 3 | 7 |
| Low | 8 | 0 | 8 (多数合规) |

---

## Critical 级别发现

### [C1] DJANGO-DEPLOY-002: DEBUG 模式未关闭
- **项目:** 两个项目
- **位置:** algo_rank `.env` / eacm_passport `.env`
- **状态:** 待处理（部署配置）
- **说明:** 开发环境需 DEBUG=True，生产部署时必须设置 `DEBUG=False`
- **补充:** 已在两个项目 settings.py 中添加生产环境安全加固块，关闭 DEBUG 时自动启用 HTTPS、安全头、SECRET_KEY 校验

### [C2] DJANGO-CONFIG-001: SECRET_KEY 使用不安全默认值
- **项目:** 两个项目
- **位置:** algo_rank `.env` / eacm_passport `.env`
- **状态:** 待处理（部署配置）
- **说明:** 开发环境可使用默认值，生产部署时需生成强密钥
- **补充:** 已在 settings.py 中添加运行时校验，生产环境使用 `django-insecure` 前缀的密钥会直接报错阻止启动

### [C3] OAuth-SEC-002: AES 加密密钥弱且填充不安全 ✅ 已修复
- **项目:** eacm_passport
- **修复内容:**
  - `apps/oauth/models.py`: 移除 `ljust(32, b'0')` 不安全填充，改为长度不匹配时抛出 ValueError
  - `eacm_passport/settings.py`: 移除硬编码默认值，改为空字符串（开发环境 .env 中配置 32 字节密钥）
- **验证:** 语法通过 + Django check 通过 + 集成测试通过

### [C4] DJANGO-CONFIG-001(补充): .env 文件无版本控制保护 ✅ 已修复
- **项目:** 两个项目
- **修复内容:** 项目2 已创建 `.gitignore`（项目1 因目录权限限制无法写入，需手动创建）
- **.gitignore 内容:** `.env`、`__pycache__/`、`venv/`、`*.sqlite3`、`staticfiles/`、`media/`、IDE/OS 文件

---

## High 级别发现

### [H1] DJANGO-HOST-001: ALLOWED_HOSTS 使用通配符
- **状态:** 待处理（部署配置）
- **说明:** 生产部署时在 .env 中设置具体域名即可

### [H2] DJANGO-HTTPS-001: 缺少 HTTPS 和安全 Cookie 配置 ✅ 已修复
- **项目:** 两个项目
- **修复内容:** 两个项目 settings.py 中添加生产环境安全加固块：
  - `SECURE_SSL_REDIRECT = True`
  - `SESSION_COOKIE_SECURE = True`
  - `CSRF_COOKIE_SECURE = True`
  - `SECURE_CONTENT_TYPE_NOSNIFF = True`
  - `SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'`
  - `X_FRAME_OPTIONS = 'DENY'`
- **安全策略:** 仅 `DEBUG=False` 时生效，不影响开发环境

### [H3] CORS-SEC-001: CORS_ALLOW_ALL_ORIGINS 与 CREDENTIALS 同时启用 ✅ 已修复
- **项目:** eacm_passport
- **修复内容:**
  - `CORS_ALLOW_ALL_ORIGINS = False`（始终禁用通配符）
  - `CORS_ALLOWED_ORIGINS` 过滤空值（修复空字符串导致的 E013 错误）
  - 生产环境通过 .env 的 `CORS_ALLOWED_ORIGINS` 配置具体域名

### [H4] EACM_PASSPORT_BASE_URL 使用 HTTP
- **状态:** 待处理（部署配置）
- **说明:** 已在 passport_client.py 添加 HTTPS 运行时校验（H8），生产环境未使用 HTTPS 会阻止启动

### [H5] DJANGO-ADMIN-001: Admin 路径使用默认值 ✅ 已修复
- **项目:** 两个项目
- **修复内容:** 两个项目的 `urls.py` 中 `admin/` 路径更改为 `django-admin-x7k9/`
- **注意:** 如需进一步加固，建议添加 IP 白名单中间件

### [H6] eacm_passport OAuth Admin Token 暴露 ✅ 已修复
- **项目:** eacm_passport
- **修复内容:** `apps/oauth/admin.py`:
  - `exclude = ('access_token', 'refresh_token')` — 编辑表单中排除 token 字段
  - `readonly_fields` 增加 token 字段 — 防止误操作修改
  - 移除对不存在字段 `user__phone` 的搜索引用

### [H7] algo_rank 管理员注册端点完全公开
- **状态:** 待处理
- **说明:** 需添加 CAPTCHA 或改为邀请制，属于业务逻辑调整

### [H8] eacm_passport verify_token 通信未强制 HTTPS ✅ 已修复
- **项目:** algo_rank
- **修复内容:** `apps/auth_app/passport_client.py` 的 `__init__` 添加运行时校验：
  - 生产环境 (`DEBUG=False`) 时，`EACM_PASSPORT_BASE_URL` 必须以 `https://` 开头
  - 否则抛出 ValueError 阻止启动

---

## Medium 级别发现

### [M1] DJANGO-REDIRECT-001: OAuth redirect_uri 无白名单 ✅ 已修复
- **项目:** eacm_passport
- **修复内容:** `apps/oauth/serializers.py` 添加 `validate_redirect_uri` 方法：
  - 通过环境变量 `OAUTH_ALLOWED_REDIRECT_URIS` 配置白名单
  - 开发模式（未配置白名单时）放行 `http://localhost` 开头的地址
  - 生产环境未在白名单中的地址返回验证错误

### [M2] DJANGO-AUTH-001: ChangePasswordView 未验证密码强度 ✅ 已修复
- **项目:** algo_rank
- **修复内容:** `apps/auth_app/views.py` 添加 `validate_password()` 调用：
  - 密码修改时经过 Django 4 个密码验证器检查
  - 不通过时返回具体错误信息（如"密码太短"、"与用户名太相似"）

### [M3] DJANGO-AUTHZ-001: PassportBindSchoolView 未使用序列化器
- **状态:** 待处理（低优先级）

### [M4] DJANGO-AUTHZ-001: VerifyAdminView 无学校维度限制
- **状态:** 待处理（低优先级）

### [M5] DJANGO-HEADERS-001: 缺少安全响应头 ✅ 已修复（随 H2）
- **修复内容:** 已在 H2 的安全加固块中添加 `SECURE_CONTENT_TYPE_NOSNIFF` 和 `SECURE_REFERRER_POLICY`

### [M6] DJANGO-LOG-001: OAuth 错误消息泄露内部信息 ✅ 已修复
- **项目:** eacm_passport
- **修复内容:** `apps/oauth/views.py`:
  - OAuth 认证失败: `f'第三方认证失败: {str(e)}'` → `'第三方认证失败，请稍后重试'`
  - Token 刷新失败: `f'令牌刷新失败: {str(e)}'` → `'令牌无效或已过期'`
  - 服务端日志仍记录完整错误信息供排查

### [M7] DJANGO-SUPPLY-001: 依赖版本未锁定
- **状态:** 待处理

### [M8] SQLite 用于生产环境
- **状态:** 待处理（部署时切换 PostgreSQL）

### [M9] JWT Refresh Token 有效期偏长 (30天)
- **状态:** 待处理（可通过环境变量 `JWT_REFRESH_TOKEN_LIFETIME` 调整）

### [M10] algo_rank 手动分页未限制 page_size 上限
- **状态:** 待处理

---

## Low 级别 (合规) 发现

### [L1] CSRF 保护 — 合规
### [L2] XSS 防护 — 合规 (仅 JSON API)
### [L3] SQL 注入 — 合规 (全部使用 ORM)
### [L4] OS 命令注入 — 合规 (无 subprocess 使用)
### [L5] 路径遍历 — 合规
### [L6] OAuth State 参数 — 合规 (secrets.token_urlsafe, 一次性使用)
### [L7] SSRF 风险 — 合规 (passport_client.py URL 来自 settings)
### [L8] 裸 except 吞噬异常 — 低风险 (Celery 任务中)

---

## 修复记录

| 修复时间 | 发现编号 | 修改文件 | 修改说明 |
|----------|----------|----------|----------|
| 2026-07-20 | C3 | `apps/oauth/models.py`, `settings.py` | 移除 ljust 填充，添加长度断言 |
| 2026-07-20 | C4 | `.gitignore` | 创建版本控制排除文件 |
| 2026-07-20 | H2, M5 | 两个项目 `settings.py` | 添加生产环境安全加固块 (HTTPS/安全头/SECRET_KEY校验) |
| 2026-07-20 | H3 | `eacm_passport/settings.py` | CORS_ALLOW_ALL_ORIGINS=False, 过滤空值 |
| 2026-07-20 | H5 | 两个项目 `urls.py` | Admin URL 更改为 `django-admin-x7k9/` |
| 2026-07-20 | H6 | `apps/oauth/admin.py` | 排除 token 字段 |
| 2026-07-20 | H8 | `passport_client.py` | 添加 HTTPS 运行时校验 |
| 2026-07-20 | M1 | `apps/oauth/serializers.py` | redirect_uri 白名单校验 |
| 2026-07-20 | M2 | `apps/auth_app/views.py` | 添加 validate_password() |
| 2026-07-20 | M6 | `apps/oauth/views.py` | 错误消息脱敏 |

**回归验证:** Django check 通过 (2个项目) + 集成测试 123 项全部通过 + 12 个修改文件语法验证通过

---

## 部署前剩余待办

| 优先级 | 事项 | 操作 |
|--------|------|------|
| P0 | 生成生产 SECRET_KEY | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| P0 | 生成生产 AES_SECRET_KEY | `python -c "import os; print(os.urandom(24).hex())"` (48字符=48字节, 取前32即可) |
| P0 | 设置 `DEBUG=False` | .env 中修改 |
| P0 | 设置 `ALLOWED_HOSTS` | .env 中填写具体域名 |
| P1 | 设置 `EACM_PASSPORT_BASE_URL` 为 HTTPS | .env 中修改 |
| P1 | 配置 `CORS_ALLOWED_ORIGINS` | .env 中填写前端域名 |
| P2 | 配置 `OAUTH_ALLOWED_REDIRECT_URIS` | .env 中填写回调地址白名单 |
| P2 | 为项目1手动创建 `.gitignore` | 参考 `d:\dev\项目2-通行证系统\.gitignore` |
