"""FastAPI / Starlette adapter.

Usage::

    from fastapi import Depends, FastAPI
    from lotus_passport import PassportClient, PassportIdentity
    from lotus_passport.integrations.fastapi import PassportAuth

    passport = PassportClient("https://passport.eacm.cn")
    require_user = PassportAuth(passport)
    optional_user = PassportAuth(passport, optional=True)

    app = FastAPI()

    @app.get("/me")
    def me(identity: PassportIdentity = Depends(require_user)):
        return {"id": identity.passport_user_id}
"""
from __future__ import annotations

from typing import Any

from ..client import PassportClient
from ..errors import PassportServiceError, TokenError, TokenExpired

_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


class PassportAuth:
    """A FastAPI dependency that turns a Bearer header into a verified identity.

    Args:
        client: A shared :class:`~lotus_passport.client.PassportClient`.
        optional: When True, an anonymous request yields ``None`` instead of 401.
        online: Call ``/userinfo`` as well, so ``avatar``/``providers`` are filled.
            Costs a round-trip per request — leave off for hot paths.

    Notes:
        Token problems become **401**; passport being unreachable becomes **503**.
        Collapsing the second case into 401 would log every user out during an
        outage, which looks exactly like a mass credential failure to on-call.
    """

    def __init__(
        self, client: PassportClient, *, optional: bool = False, online: bool = False
    ) -> None:
        self._client = client
        self._optional = optional
        self._online = online

    def __call__(self, request: Any) -> Any:
        from fastapi import HTTPException, status

        header = request.headers.get("authorization")
        token = self._client.extract_bearer(header)
        if token is None:
            if self._optional:
                return None
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少 Authorization: Bearer <token> 请求头",
                headers=_BEARER_CHALLENGE,
            )

        try:
            if self._online:
                return self._client.get_userinfo(token)
            return self._client.verify_token(token)
        except TokenExpired as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="访问令牌已过期，请使用 refresh token 续期",
                headers=_BEARER_CHALLENGE,
            ) from exc
        except TokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"令牌无效: {exc}",
                headers=_BEARER_CHALLENGE,
            ) from exc
        except PassportServiceError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"认证中心暂时不可用: {exc}",
            ) from exc


__all__ = ["PassportAuth"]
