"""
Lotus Passport — Django settings.

Design principles (see project spec):
  * Standalone unified auth center. Issues a unified JWT.
  * Does IDENTITY only — never business permissions.
  * Third-party OAuth access_tokens are stored AES-256-CBC encrypted.
  * Redis is used for rate limiting + OAuth state (short-lived, TTL'd).
  * Dev: SQLite. Prod: PostgreSQL (configure DATABASE_URL).
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# True when running under pytest (pytest is imported first by pytest-django).
TESTING = "pytest" in sys.modules


def _load_dotenv(path: Path) -> None:
    """Populate os.environ from a .env file, without pulling in python-dotenv.

    Real environment variables always win, so `DEBUG=0 ./manage.py ...` still
    overrides the file. Deliberately minimal: KEY=VALUE per line, `#` comments,
    optional surrounding quotes. No interpolation, no export keyword.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# WebAuthn / Passkey (§9.4b)
# --------------------------------------------------------------------------- #
# RP = Relying Party. The RP ID must be a suffix of the origin the browser
# performs the ceremony on. In dev the SPA runs on :3000 and the API on :8000;
# both are listed so localhost passkeys register/assert against either origin.
PASSPORT_RP_ID = env("PASSPORT_RP_ID", "localhost")
PASSPORT_RP_NAME = env("PASSPORT_RP_NAME", "莲花通行证")
WEBAUTHN_ORIGINS = [
    o.strip()
    for o in env(
        "WEBAUTHN_ORIGINS", "http://localhost:3000,http://localhost:8000"
    ).split(",")
    if o.strip()
]


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
SECRET_KEY = env("SECRET_KEY", "dev-insecure-secret-change-me-in-production")

# Our unified identity model is the project's user model (not Django's default).
AUTH_USER_MODEL = "passport.PassportUser"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
DEBUG = env_bool("DEBUG", True)  # dev-friendly default; set to False in production
ALLOWED_HOSTS = [h for h in env("ALLOWED_HOSTS", "*").split(",") if h]

# Stub login endpoints (api/v1/dev/*) used by the SPA to exercise the full
# login → JWT → userinfo loop without real OAuth apps. This is a SEPARATE
# switch from DEBUG on purpose: a DEBUG=True production accident must not
# silently expose a stub login. Defaults to DEBUG so local dev "just works",
# but production should set DEBUG=False (which also forces this off unless
# explicitly opted in). Flip with ENABLE_DEV_LOGIN=True/False.
ENABLE_DEV_LOGIN = env_bool("ENABLE_DEV_LOGIN", default=DEBUG)

# Detected automatically by pytest-django; explicit here for clarity.
TESTING = "pytest" in sys.modules

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "passport",
]

MIDDLEWARE = [
    "passport.middleware.TrustedProxyMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "passport.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "passport.wsgi.application"
ASGI_APPLICATION = "passport.asgi.application"

# --------------------------------------------------------------------------- #
# Database: SQLite (dev) / PostgreSQL (prod via DATABASE_URL)
# --------------------------------------------------------------------------- #
DATABASE_URL = env("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres"):
    import dj_database_url  # type: ignore  # noqa: F401  (optional in prod)

    DATABASES = {"default": dj_database_url.config(default=DATABASE_URL)}  # type: ignore
else:
    # WAL 是常规环境下的最佳选择：读写不互斥、吞吐高。
    #
    # 但它依赖「最后一个连接关闭时删除 db-wal / db-shm 两个附属文件」。
    # 在某些受管沙箱 / 容器里文件删除会被拦截（改写成「移入回收站」），
    # SQLite 的 unlink 因此变成秒级阻塞甚至直接让进程中止 —— 表现为随机的
    # "database is locked"。DELETE 模式同理（每次提交都要删 db-journal）。
    #
    # TRUNCATE 把日志文件截断成 0 字节而不是删除它，既保留崩溃恢复能力，
    # 又完全不触发 unlink。所以这里做成可配置：正常环境用 WAL，
    # 受限环境在 .env 里设 SQLITE_JOURNAL_MODE=TRUNCATE 即可。
    _JOURNAL_MODE = env("SQLITE_JOURNAL_MODE", "WAL").upper()
    _SYNCHRONOUS = "NORMAL" if _JOURNAL_MODE == "WAL" else "FULL"
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": env("DB_PATH", str(BASE_DIR / "db.sqlite3")),
            "OPTIONS": {
                # 默认 5s 超时在并发登录时不够用，直接撞 "database is locked"。
                "timeout": 20,
                # busy_timeout 与上面的 timeout 对应，覆盖 PRAGMA 层。
                "init_command": (
                    f"PRAGMA journal_mode={_JOURNAL_MODE};"
                    f"PRAGMA synchronous={_SYNCHRONOUS};"
                    "PRAGMA busy_timeout=20000;"
                ),
                # 写事务一开始就拿写锁，避免「读→升级为写」时才发现冲突而直接失败。
                "transaction_mode": "IMMEDIATE",
            },
        }
    }

# --------------------------------------------------------------------------- #
# Redis: rate limiting + OAuth state store
# --------------------------------------------------------------------------- #
REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")

# --------------------------------------------------------------------------- #
# Password validation (unused for OAuth login, kept for admin account safety)
# --------------------------------------------------------------------------- #
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# --------------------------------------------------------------------------- #
# Internationalization
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = env("STATIC_ROOT", str(BASE_DIR / "staticfiles"))
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

# --------------------------------------------------------------------------- #
# 用户上传媒体（头像等）。开发期由 urls.py 的 static() 直接吐；生产由 Nginx 反代。
# avatar 字段存的是相对 URL（/media/avatars/xxx.png），前端经同源 /media 代理加载。
# --------------------------------------------------------------------------- #
MEDIA_URL = env("MEDIA_URL", "media/")
MEDIA_ROOT = env("MEDIA_ROOT", str(BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# CORS — allowed origins are the integrating apps (项目1 / e-algo rank 前端已预置:
# rank.eacm.cn；本机前端 account.eacm.cn 亦已预置)。详见 docs/integration/project1-ealgo-rank.md。
# --------------------------------------------------------------------------- #
CORS_ALLOWED_ORIGINS = [o for o in env("CORS_ALLOWED_ORIGINS", "").split(",") if o]
if DEBUG or TESTING:
    CORS_ALLOWED_ORIGINS += ["http://localhost:3000", "http://127.0.0.1:3000"]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_HEADERS = ["authorization", "content-type", "x-requested-with"]

# --------------------------------------------------------------------------- #
# DRF
# --------------------------------------------------------------------------- #
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "EXCEPTION_HANDLER": "passport.exceptions.custom_exception_handler",
}

# --------------------------------------------------------------------------- #
# JWT (djangorestframework-simplejwt)
#   - RS256 with an RSA keypair is the DEFAULT. The whole point of a unified
#     auth center is that integrators verify with the PUBLIC key via JWKS — never
#     a shared secret.
#   - HS256 remains available via JWT_USE_RS256=False (shared-secret integrators
#     only).
#   The unified claim `passport_user_id` is added in passport.jwt.issue_tokens.
# --------------------------------------------------------------------------- #
# --- RSA keypair for RS256 (managed by KeyStore; supports rotation) --------- #
# Resolution order: explicit env PEM (PASSPORT_JWT_PRIVATE_KEY/PUBLIC_KEY) ->
# KeyStore files in PASSPORT_JWT_KEYS_DIR (manifest.json + private_<kid>.pem /
# public_<kid>.pem) -> (DEBUG only) auto-generate the initial keypair so the
# local stack runs out of the box. Production MUST ship real keys (env PEM or
# pre-generated files) and never auto-generate. Rotation is `manage.py rotate_keys`.
from .keys import KeyStore

JWT_KEYS_DIR = env("PASSPORT_JWT_KEYS_DIR", str(BASE_DIR / "keys"))
JWT_KID = env("JWT_KID", "lotus-passport-rsa-1")
JWT_USE_RS256 = env_bool("JWT_USE_RS256", True)

key_store = KeyStore(JWT_KEYS_DIR, initial_kid=JWT_KID)
_env_priv = env("PASSPORT_JWT_PRIVATE_KEY")
_env_pub = env("PASSPORT_JWT_PUBLIC_KEY")
if _env_priv and _env_pub:
    key_store.load_env(_env_priv, _env_pub)

# `manage.py generate_keys` is the command that CREATES the keypair, so it must
# be able to boot without one — otherwise production is a chicken-and-egg
# deadlock (settings refuses to load => the bootstrap command can never run).
_BOOTSTRAP_COMMAND = len(sys.argv) > 1 and sys.argv[1] == "generate_keys"

if JWT_USE_RS256 and not key_store.has_keys:
    if DEBUG and not (_env_priv and _env_pub):
        # Zero-config dev: auto-generate the initial keypair + manifest.
        key_store.ensure_initial(kid=JWT_KID)
    elif not _BOOTSTRAP_COMMAND:
        raise RuntimeError(
            "RSA keypair for RS256 missing. Run `python manage.py generate_keys` "
            "(writes keys/ keypair + manifest) or set PASSPORT_JWT_PRIVATE_KEY / "
            "PASSPORT_JWT_PUBLIC_KEY."
        )

if JWT_USE_RS256 and key_store.has_keys:
    JWT_ALGORITHM = "RS256"
    JWT_SIGNING_KEY = key_store.active_private_pem
    JWT_VERIFYING_KEY = key_store.active_public_pem
    # Keep JWT_KID in sync with the active key so issued tokens + JWKS agree.
    JWT_KID = key_store.active_kid
else:
    # Either HS256 was explicitly requested (legacy shared-secret integrators),
    # or we're inside `generate_keys` and the RSA keys do not exist yet — that
    # process issues no tokens, so a throwaway HS256 backend is harmless.
    JWT_ALGORITHM = "HS256"
    JWT_SIGNING_KEY = env("JWT_SIGNING_KEY", SECRET_KEY)
    JWT_VERIFYING_KEY = None

# `iss` claim. Integrators SHOULD pin this (the SDK does by default) so a token
# minted by some other RS256 issuer can never be replayed here. Kept as a plain
# opaque string rather than a URL: it must stay stable across deployments even
# if the public hostname changes.
JWT_ISSUER = env("JWT_ISSUER", "lotus-passport")

# Expose the key store as a Django setting so jwt/views/apps can reach it via
# `settings.KEY_STORE` (a plain module-local var would not be visible there).
KEY_STORE = key_store

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_TTL_MIN", "30"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_TTL_DAYS", "14"))),
    "ALGORITHM": JWT_ALGORITHM,
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "VERIFYING_KEY": JWT_VERIFYING_KEY,
    # Emitted into every token and verified on the way back in.
    "ISSUER": JWT_ISSUER,
    # Stamp every token with the JWKS `kid` so integrators can pin the key.
    # Note: simplejwt 5.5.1 has NO TOKEN_BACKEND setting, so the `kid` is injected
    # via the custom token classes in passport.jwt (PassportRefreshToken/AccessToken).
    # Our user model's PK is `id` (not a `user_id` column), so point simplejwt at it.
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
}

# --------------------------------------------------------------------------- #
# Token encryption (AES-256-CBC) for third-party access_tokens
#   TOKEN_ENCRYPTION_KEY = base64(32 bytes). Generate:
#   python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"
# --------------------------------------------------------------------------- #
TOKEN_ENCRYPTION_KEY = env(
    "TOKEN_ENCRYPTION_KEY",
    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",  # dev placeholder
)

# --------------------------------------------------------------------------- #
# OAuth providers — client id/secret from env. Redirect base shared by all.
# --------------------------------------------------------------------------- #
PASSPORT_OAUTH_REDIRECT_BASE = env(
    "PASSPORT_OAUTH_REDIRECT_BASE", "http://localhost:8000/api/v1/oauth"
)
FRONTEND_SUCCESS_REDIRECT = env("FRONTEND_SUCCESS_REDIRECT", "http://localhost:3000/")

OAUTH_PROVIDERS = {
    "github": {
        "client_id": env("GITHUB_CLIENT_ID", ""),
        "client_secret": env("GITHUB_CLIENT_SECRET", ""),
    },
    "wechat": {
        "client_id": env("WECHAT_CLIENT_ID", ""),
        "client_secret": env("WECHAT_CLIENT_SECRET", ""),
    },
    "qq": {
        "client_id": env("QQ_CLIENT_ID", ""),
        "client_secret": env("QQ_CLIENT_SECRET", ""),
    },
}

# Allow-list of post-login redirect_uri values (open-redirect mitigation, A-11).
# Empty => only localhost/127.0.0.1 is permitted, and only while DEBUG/TESTING
# (mirrors the CORS auto-allow). In production this MUST list every integrating
# app's callback origin (origin-only entry allows any path) or exact
# "origin/path" (exact match). See passport/redirects.py for match semantics.
# 已预置: account.eacm.cn (本机前端) 与 rank.eacm.cn (项目1 / e-algo rank),
# 供其后续接入 —— 无需再改 passport 配置即可用统一登录。详见
# docs/integration/project1-ealgo-rank.md。
OAUTH_ALLOWED_REDIRECT_URIS = [
    o.strip() for o in env("OAUTH_ALLOWED_REDIRECT_URIS", "").split(",") if o.strip()
]

# Server-side token revocation (real logout). When True, POST /api/v1/logout/
# adds the token's jti to a Redis blacklist and /api/v1/userinfo/ rejects a
# revoked jti. Integrators that verify tokens OFFLINE (via JWKS) only stop
# trusting a revoked token on its natural expiry — bounded by the short access
# TTL. The store degrades OPEN if Redis is unavailable. See HANDOVER §7.
TOKEN_REVOCATION_ENABLED = env_bool("TOKEN_REVOCATION_ENABLED", True)

# Rate limit applied to sensitive endpoints (login / callback).
RATE_LIMIT_LOGIN = (20, 60)       # 20 requests / 60s per account (identifier dimension)
RATE_LIMIT_CALLBACK = (30, 60)
# Coarse, IP-only edge limit — protects the server from a single source
# hammering many accounts. NOT an account-protection control (see §一 of the
# hardening plan: IP must never be a user dimension under NAT/CGNAT).
RATE_LIMIT_GLOBAL_IP = (200, 60)  # 200 requests / 60s per source IP

# Account-level brute-force lockout (PasswordLoginView).
ACCOUNT_LOCKOUT_THRESHOLD = 5     # consecutive failures before lock
ACCOUNT_LOCKOUT_WINDOW = 900      # seconds the lock (and counter) lives (15 min)

# Hard cap on concurrent sessions per user (§一.F). 0 disables the cap.
MAX_SESSIONS_PER_USER = 10

# Trusted reverse-proxy CIDRs. `X-Forwarded-For` is only honoured when the
# immediate peer (REMOTE_ADDR) sits in one of these ranges; otherwise it is
# ignored so a client cannot spoof its IP. Narrow this to your real proxy(ies)
# in production.
TRUSTED_PROXY_CIDRS = env(
    "TRUSTED_PROXY_CIDRS",
    "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
).split(",")

# CAPTCHA (hCaptcha) — human verification after repeated failures (§一.C).
# Disabled unless HCAPTCHA_SECRET_KEY is set, so it never affects existing
# login behaviour or the test suite. See docs/captcha-plan.md.
HCAPTCHA_SECRET_KEY = env("HCAPTCHA_SECRET_KEY", "")
CAPTCHA_PROVIDER = env("CAPTCHA_PROVIDER", "hcaptcha")
CAPTCHA_TRIGGER_THRESHOLD = int(env("CAPTCHA_TRIGGER_THRESHOLD", "3"))
CAPTCHA_ENABLED = bool(HCAPTCHA_SECRET_KEY)

LOGIN_URL = "/api/v1/oauth/github/login/"
LOGIN_REDIRECT_URL = FRONTEND_SUCCESS_REDIRECT

# --------------------------------------------------------------------------- #
# Production hardening — only when serving real traffic (not DEBUG, not TESTING)
# --------------------------------------------------------------------------- #
# When DEBUG is off we assume the app sits behind the nginx reverse proxy, which
# terminates TLS. These settings make Django correctly interpret the forwarded
# proto and harden cookies/transport. They must NOT apply in tests or dev.
if not DEBUG and not TESTING:
    # nginx sets X-Forwarded-Proto: https — tell Django to trust it so
    # request.is_secure() is correct and the secure-cookie flags behave.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

    # Cookies only over HTTPS; auth/OAuth state can't leak over plaintext.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # HTTP -> HTTPS redirect (Django-side; nginx can also do it at the edge).
    # Default OFF on purpose: the shipped compose stack listens on plain :80
    # (the TLS server block in nginx/nginx.conf is commented out until real
    # certs exist). Turning this on there produces an infinite redirect loop,
    # because X-Forwarded-Proto stays "http" and there is no 443 listener.
    # Flip SECURE_SSL_REDIRECT=True the moment TLS is live — `manage.py check
    # --deploy` (security.W008) will keep nagging until you do.
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)

    # Internal health probe: the Docker healthcheck hits
    # http://127.0.0.1:8000/api/v1/dev/status/ over plain HTTP. Exempt it from
    # the HTTP->HTTPS redirect so the probe gets 200 (not 301) and the container
    # reports healthy. No auth/secret is exposed by this endpoint.
    SECURE_REDIRECT_EXEMPT = ["api/v1/dev/status/", "/api/v1/dev/status/"]

    # HSTS: browsers must use HTTPS for a year (incl. subdomains). nginx also
    # sends this header on the 443 block; this is the Django-side backup.
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Don't reflect the Referer to third parties.
    SECURE_REFERRER_POLICY = "no-referrer"
