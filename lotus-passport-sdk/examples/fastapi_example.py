"""Minimal FastAPI service protected by Lotus Passport (RS256 JWT).

Why this shape:
- One ``PassportClient`` at module scope. It owns the JWKS cache, so reusing it
  means a JWKS fetch only on first unknown ``kid`` (and on rotation), not per request.
- ``require_user`` is a FastAPI dependency. It returns a verified
  ``PassportIdentity``; the route never sees the raw token.

Run (from the repo root, with a venv that has the sdk + fastapi installed):

    uv run --extra fastapi python examples/fastapi_example.py
    # or:
    uvicorn examples.fastapi_example:app --reload

Then call it with a real passport access token:

    curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/me

To get a token locally, see the passport README §2.2 (Dev 模拟登录) / §7.4.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI

from lotus_passport import PassportClient, PassportIdentity
from lotus_passport.integrations.fastapi import PassportAuth

# Replace with your deployment root (no trailing slash needed).
PASSPORT_BASE_URL = "https://passport.eacm.cn"

# One shared client per process — it owns the JWKS cache.
passport = PassportClient(PASSPORT_BASE_URL)

require_user = PassportAuth(passport)
# optional_user lets anonymous requests through (identity becomes None).
optional_user = PassportAuth(passport, optional=True)
# online=True also hits /userinfo for avatar + linked providers (one extra
# round-trip per request — leave off for hot paths).
require_user_online = PassportAuth(passport, online=True)

app = FastAPI(title="algo_rank (example)")


@app.get("/public")
def public() -> dict:
    return {"msg": "anyone can see this"}


@app.get("/me")
def me(identity: PassportIdentity = Depends(require_user)) -> dict:
    # identity.passport_user_id is your STABLE join key — store it on the local
    # user row (unique, indexed). Never join on email (users change it).
    return {
        "passport_user_id": identity.passport_user_id,
        "email": identity.email,
        "nickname": identity.nickname,
        "source": identity.source,  # "jwt" (offline) in this route
    }


@app.get("/profile")
def profile(identity: PassportIdentity = Depends(require_user_online)) -> dict:
    return {
        "passport_user_id": identity.passport_user_id,
        "avatar": identity.avatar,
        "providers": list(identity.providers),
    }


# Bonus: a dependency that only checks "is this a valid token" without needing
# the user to map onto a local row.
@app.get("/ping")
def ping(identity: PassportIdentity = Depends(optional_user)) -> dict:
    if identity is None:
        return {"authenticated": False}
    return {"authenticated": True, "passport_user_id": identity.passport_user_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
