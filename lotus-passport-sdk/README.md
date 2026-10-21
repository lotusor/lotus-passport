# lotus-passport-sdk (Python)

Verify **Lotus Passport** unified-auth JWTs in any Python service — without  
re-implementing crypto, without sharing secrets, and without trusting the token's  
own `alg` header.

- RS256 asymmetric verification against the public **JWKS** (`/.well-known/jwks.json`)
- **Offline** by default: `verify_token()` does zero network I/O on the hot path
- **Algorithm-confusion safe**: the accepted algorithm is pinned from an allow-list,  
  never read from the token. `none` / `HS256/384/512` are rejected at construction.
- **Outage resilient**: a passport blip becomes `503`, not a mass-401 logout
- Framework adapters for **FastAPI**, **Django REST Framework**, **Flask**  
  (imported lazily — the SDK never drags in a web framework you don't use)

```bash
pip install "lotus-passport-sdk"                 # core (PyJWT + requests)
pip install "lotus-passport-sdk[fastapi]"        # + FastAPI adapter
pip install "lotus-passport-sdk[drf]"            # + DRF adapter
pip install "lotus-passport-sdk[flask]"          # + Flask adapter
```

> Requirements: Python ≥ 3.9, `PyJWT[crypto] >= 2.8`, `requests >= 2.28`.  
> The `requests` dependency is optional — pass your own `transport=` to avoid it.

---

## 1. Quickstart

```python
from lotus_passport import PassportClient

# One client per process — it owns the JWKS cache.
passport = PassportClient("https://passport.eacm.cn")

identity = passport.verify_token(access_token)   # str token, no "Bearer " prefix
print(identity.passport_user_id)                 # your stable join key (UUID)
print(identity.email, identity.nickname)
```

`identity.passport_user_id` is the **only stable identifier** — store it on your  
local user row (unique, indexed). Never join on `email` (users change it).

---

## 2. Two verification modes

| Method                | Network                             | Freshness                                         | Use for                                                         |
| --------------------- | ----------------------------------- | ------------------------------------------------- | --------------------------------------------------------------- |
| `verify_token()`      | **None** (uses cached JWKS)         | As fresh as the token (≤ `ACCESS_TOKEN_LIFETIME`) | Every request — fast, survives passport outages                 |
| `get_userinfo(token)` | 1 round-trip to `/api/v1/userinfo/` | Live — returns `avatar` + linked `providers`      | First sight of a user (provision row), explicit profile refresh |

Recommended pattern: `verify_token()` on every request; call `get_userinfo()`  
only when you first see a `passport_user_id` (to fill avatar/providers) or when  
the user explicitly refreshes their profile.

```python
identity = passport.verify_token(token)              # offline
if not local_user_exists(identity.passport_user_id):
    full = passport.get_userinfo(token)              # online enrichment
    create_local_user(full)
```

---

## 3. Framework adapters

### FastAPI

```python
from fastapi import Depends, FastAPI
from lotus_passport import PassportClient, PassportIdentity
from lotus_passport.integrations.fastapi import PassportAuth

passport = PassportClient("https://passport.eacm.cn")
require_user = PassportAuth(passport)
optional_user = PassportAuth(passport, optional=True)     # None when anonymous

app = FastAPI()

@app.get("/me")
def me(identity: PassportIdentity = Depends(require_user)):
    return {"id": identity.passport_user_id}
```

The dependency maps failures to HTTP: **bad token → 401**, **passport  
unreachable → 503** (with a `WWW-Authenticate: Bearer` challenge).

### Django REST Framework

```python
# settings.py
LOTUS_PASSPORT = {
    "BASE_URL": "https://passport.eacm.cn",
    "ISSUER": "lotus-passport",
    "AUTO_CREATE_USER": True,
    # "USER_RESOLVER": "myapp.auth.resolve_passport_user",  # optional override
}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "lotus_passport.integrations.drf.PassportAuthentication",
    ],
}
```

```python
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    identity = request.auth          # verified PassportIdentity
    return Response({"id": identity.passport_user_id})
```

The adapter verifies offline and then resolves the identity onto a local Django  
user. By default it matches a `passport_user_id` field (or `USERNAME_FIELD`),  
auto-creating the row on first sight when `AUTO_CREATE_USER=True`. Set  
`AUTO_CREATE_USER=False` for invite-only services.

### Flask

```python
from flask import Flask, g, jsonify
from lotus_passport import PassportClient
from lotus_passport.integrations.flask import passport_required

passport = PassportClient("https://passport.eacm.cn")
app = Flask(__name__)

@app.get("/me")
@passport_required(passport)
def me():
    return jsonify(passport_user_id=g.passport_identity.passport_user_id)
```

---

## 4. Configuration

```python
PassportClient(
    base_url,                       # "https://passport.eacm.cn" (trailing slash optional)
    issuer="lotus-passport",        # pin iss; None disables the check (legacy only)
    audience=None,                  # expected aud; None = don't check
    algorithms=("RS256",),         # symmetric algs are rejected at construction
    leeway=30,                     # clock-skew tolerance (seconds) on exp/iat
    cache_ttl=600.0,               # JWKS cache lifetime (seconds)
    min_refresh_interval=30.0,     # throttle for unknown-kid forced refreshes (anti-DoS)
    timeout=5.0,                   # HTTP timeout (seconds)
    transport=None,                # plug your own Transport (httpx, aiohttp, test stub)
)
```

Endpoints are derived from `base_url` but can be overridden:  
`jwks_url`, `userinfo_url`, `refresh_url`, or adopted at runtime via `discover()`  
(which reads `/.well-known/passport-configuration`).

### Custom transport (zero hard HTTP dependency)

The SDK talks through a `Transport` protocol (`get_json` / `post_json`). Tests  
use an in-memory stub; async users can plug `httpx`. See  
`examples/standalone_verify.py` for a fully offline runnable demo.

---

## 5. Security model

| Threat                                                            | How the SDK defends                                                                                                                                    |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Algorithm confusion** (`alg:none`, `HS256` with the public key) | Accepted algorithms are pinned from an allow-list at construction; the token's own `alg` is never trusted. Symmetric algs are a `PassportConfigError`. |
| **Forged `kid` amplification DoS**                                | Unknown `kid` triggers a *throttled* forced JWKS refresh; concurrent cold starts coalesce onto one in-flight fetch.                                    |
| **Replay from another RS256 issuer**                              | `iss` is pinned (`issuer=`). A token signed by a different IdP is rejected.                                                                            |
| **Mass logout on passport outage**                                | JWKS is cached (TTL) and survives short outages; only genuine token problems return 401, service problems return 503.                                  |
| **Stale/symmetric keys in JWKS**                                  | `oct` and `use:enc` keys are dropped from the public JWKS before use.                                                                                  |

---

## 6. Error → HTTP mapping

| Exception                            | Meaning                                                   | HTTP                       |
| ------------------------------------ | --------------------------------------------------------- | -------------------------- |
| `TokenExpired`                       | Signature OK but `exp` passed                             | **401**                    |
| `TokenInvalid`                       | Malformed / wrong `iss` / missing claim / bad signature   | **401**                    |
| `UnknownSigningKey`                  | `kid` not in published JWKS                               | **401**                    |
| `PassportServiceError` / `JWKSError` | passport or JWKS unreachable/garbage                      | **503**                    |
| `PassportConfigError`                | Bad client config (empty `base_url`, unsafe `algorithms`) | — (raised at construction) |

Adapters automatically translate these into the right status: **401 for token  
problems, 503 for service problems**. Getting this wrong is how an auth-server  
blip turns into "everyone got logged out".

---

## 7. Examples

Runnable, framework-specific samples live in [`examples/`](./examples):

- `fastapi_example.py` — protected FastAPI routes (`/me`, `/profile`, `/ping`)
- `flask_example.py` — protected Flask routes (`/me`, `/profile`, `/public`)
- `drf_example.py` — standalone DRF view (boots, proves 401 on anonymous)
- `standalone_verify.py` — **fully offline** smoke test (mints + verifies a token  
  via an in-memory transport; ideal for CI)

Run them from the SDK root with the relevant extra installed:

```bash
uv run --extra fastapi python examples/fastapi_example.py
uv run --extra flask   python examples/flask_example.py
uv run --extra drf     python examples/drf_example.py
uv run                 python examples/standalone_verify.py   # no extra deps
```



---

## 8. Testing

```bash
pytest                                         # 60+ tests, fully offline
```

The suite covers algorithm-confusion rejection, key rotation, outage-grade  
resilience, throttle/coalescing, and all three framework adapters (including a  
real DRF integration test against an in-memory SQLite).
