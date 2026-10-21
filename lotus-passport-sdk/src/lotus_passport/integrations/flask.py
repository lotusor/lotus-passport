"""Flask adapter.

Usage::

    from flask import Flask, g, jsonify
    from lotus_passport import PassportClient
    from lotus_passport.integrations.flask import passport_required

    app = Flask(__name__)
    passport = PassportClient("https://passport.eacm.cn")

    @app.get("/me")
    @passport_required(passport)
    def me():
        return jsonify(passport_user_id=g.passport_identity.passport_user_id)
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from ..client import PassportClient
from ..errors import PassportServiceError, TokenError, TokenExpired


def passport_required(
    client: PassportClient, *, optional: bool = False, online: bool = False
) -> Callable:
    """Decorator that verifies the Bearer token and populates ``g.passport_identity``.

    Args:
        client: Shared :class:`~lotus_passport.client.PassportClient`.
        optional: Allow anonymous access (``g.passport_identity`` becomes ``None``).
        online: Also call ``/userinfo`` for avatar + linked providers.

    Returns:
        A decorator. Failures short-circuit with a JSON body and 401 (bad token)
        or 503 (passport unreachable).
    """

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args: Any, **kwargs: Any):
            from flask import g, jsonify, request

            token = client.extract_bearer(request.headers.get("Authorization"))
            if token is None:
                if optional:
                    g.passport_identity = None
                    return view(*args, **kwargs)
                return (
                    jsonify(error={"code": 401, "message": "缺少 Bearer 令牌"}),
                    401,
                    {"WWW-Authenticate": "Bearer"},
                )
            try:
                g.passport_identity = (
                    client.get_userinfo(token) if online else client.verify_token(token)
                )
            except TokenExpired:
                return (
                    jsonify(error={"code": 401, "message": "访问令牌已过期"}),
                    401,
                    {"WWW-Authenticate": "Bearer"},
                )
            except TokenError as exc:
                return (
                    jsonify(error={"code": 401, "message": f"令牌无效: {exc}"}),
                    401,
                    {"WWW-Authenticate": "Bearer"},
                )
            except PassportServiceError as exc:
                return (
                    jsonify(error={"code": 503, "message": f"认证中心暂时不可用: {exc}"}),
                    503,
                )
            return view(*args, **kwargs)

        return wrapper

    return decorator


__all__ = ["passport_required"]
