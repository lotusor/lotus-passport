"""Minimal Flask app protected by Lotus Passport (RS256 JWT).

The ``passport_required`` decorator verifies the Bearer token and stores the
result on ``g.passport_identity``. Token problems -> 401 JSON, passport
unreachable -> 503 JSON (see the SDK error taxonomy).

Run (from the repo root):

    uv run --extra flask python examples/flask_example.py

Then:

    curl -H "Authorization: Bearer <token>" http://127.0.0.1:5000/me
"""
from __future__ import annotations

from flask import Flask, g, jsonify

from lotus_passport import PassportClient
from lotus_passport.integrations.flask import passport_required

PASSPORT_BASE_URL = "https://passport.eacm.cn"

# One shared client per process.
passport = PassportClient(PASSPORT_BASE_URL)
app = Flask(__name__)


@app.get("/me")
@passport_required(passport)
def me():
    identity = g.passport_identity
    return jsonify(
        passport_user_id=identity.passport_user_id,
        email=identity.email,
        nickname=identity.nickname,
    )


@app.get("/profile")
@passport_required(passport, online=True)
def profile():
    identity = g.passport_identity
    return jsonify(
        passport_user_id=identity.passport_user_id,
        avatar=identity.avatar,
        providers=list(identity.providers),
    )


@app.get("/public")
@passport_required(passport, optional=True)
def public():
    if g.passport_identity is None:
        return jsonify(who="anonymous")
    return jsonify(passport_user_id=g.passport_identity.passport_user_id)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
