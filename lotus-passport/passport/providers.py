"""
OAuth2 providers: GitHub, WeChat, QQ.

Each provider normalizes a third-party login into a single :class:`Identity`,
which the view links to (or creates) a PassportUser. Third-party access_tokens
are encrypted before persistence (see models.OAuthAccount).

* GitHub / WeChat use authlib's OAuth2Session for the token exchange.
* QQ uses a hand-rolled exchange (non-standard urlencoded/openid-in-me quirks)
  but the same normalized Identity contract.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode

import requests
from authlib.integrations.requests_client import OAuth2Session
from django.conf import settings


@dataclass
class Identity:
    provider_user_id: str
    email: str | None
    nickname: str
    avatar: str = ""


class BaseProvider(ABC):
    name: str = ""
    authorize_url: str = ""
    token_url: str = ""
    scope: str = ""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    # ---- public API ------------------------------------------------------- #
    def get_authorize_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "state": state,
        }
        return f"{self.authorize_url}?{urlencode(params)}"

    @abstractmethod
    def exchange_code(self, code: str) -> tuple[dict, datetime | None]:
        """Exchange `code` for a raw token dict + optional expires_at."""

    @abstractmethod
    def fetch_identity(self, raw_token: dict) -> Identity:
        """Turn a raw token into a normalized Identity."""

    # ---- helpers ---------------------------------------------------------- #
    def _expires_at(self, token: dict) -> datetime | None:
        exp = token.get("expires_in")
        if exp:
            return datetime.now(timezone.utc) + timedelta(seconds=int(exp))
        return None


class GitHubProvider(BaseProvider):
    name = "github"
    authorize_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    scope = "read:user user:email"
    userinfo_url = "https://api.github.com/user"
    emails_url = "https://api.github.com/user/emails"

    def exchange_code(self, code: str):
        session = OAuth2Session(
            self.client_id,
            self.client_secret,
            scope=self.scope,
            redirect_uri=self.redirect_uri,
            token_endpoint_auth_method="client_secret_post",
        )
        token = session.fetch_token(
            self.token_url, code=code, headers={"Accept": "application/json"}
        )
        return token, self._expires_at(token)

    def fetch_identity(self, raw_token: dict) -> Identity:
        at = raw_token["access_token"]
        headers = {
            "Authorization": f"Bearer {at}",
            "Accept": "application/vnd.github+json",
        }
        user = requests.get(self.userinfo_url, headers=headers, timeout=10).json()
        email = user.get("email")
        if not email:
            try:
                emails = requests.get(self.emails_url, headers=headers, timeout=10).json()
                primary = next(
                    (e for e in emails if e.get("primary") and e.get("verified")), None
                )
                email = primary["email"] if primary else None
            except Exception:  # noqa: BLE001
                email = None
        return Identity(
            provider_user_id=str(user["id"]),
            email=email,
            nickname=user.get("login") or user.get("name") or "",
            avatar=user.get("avatar_url") or "",
        )


class WeChatProvider(BaseProvider):
    name = "wechat"
    authorize_url = "https://open.weixin.qq.com/connect/qrconnect"
    token_url = "https://api.weixin.qq.com/sns/oauth2/access_token"
    scope = "snsapi_login"
    userinfo_url = "https://api.weixin.qq.com/sns/userinfo"

    def exchange_code(self, code: str):
        session = OAuth2Session(
            self.client_id,
            self.client_secret,
            scope=self.scope,
            redirect_uri=self.redirect_uri,
            token_endpoint_auth_method="client_secret_post",
        )
        token = session.fetch_token(
            self.token_url, code=code, headers={"Accept": "application/json"}
        )
        return token, self._expires_at(token)

    def fetch_identity(self, raw_token: dict) -> Identity:
        at = raw_token["access_token"]
        openid = raw_token.get("openid")
        unionid = raw_token.get("unionid")
        params = {"access_token": at, "openid": openid}
        data = requests.get(self.userinfo_url, params=params, timeout=10).json()
        return Identity(
            provider_user_id=unionid or openid,
            email=None,
            nickname=data.get("nickname") or "",
            avatar=data.get("headimgurl") or "",
        )


class QQProvider(BaseProvider):
    name = "qq"
    authorize_url = "https://graph.qq.com/oauth2.0/authorize"
    token_url = "https://graph.qq.com/oauth2.0/token"
    scope = "get_user_info"
    me_url = "https://graph.qq.com/oauth2.0/me"
    userinfo_url = "https://graph.qq.com/user/get_user_info"

    def exchange_code(self, code: str):
        resp = requests.post(
            self.token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
                "fmt": "json",
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        # QQ ignores the Accept header and returns `text/html` even when fmt=json
        # yields a JSON body, so Content-Type is unreliable. Try JSON first, then
        # fall back to the urlencoded form.
        try:
            token = resp.json()
        except ValueError:
            token = dict(parse_qsl(resp.text))
        # QQ returns an error payload (no access_token) on failure, e.g.
        # {"error": 100007, "error_description": "client_secret error"} or the
        # urlencoded equivalent. Without this check the missing key bubbles up
        # as a misleading `KeyError: 'access_token'` 502.
        if "error" in token:
            desc = token.get("error_description") or token.get("error")
            raise ValueError(f"QQ 令牌接口返回错误: {desc}")
        return token, self._expires_at(token)

    def fetch_identity(self, raw_token: dict) -> Identity:
        at = raw_token.get("access_token")
        if not at:
            raise ValueError("QQ 令牌响应缺少 access_token 字段")
        me_text = requests.get(
            self.me_url, params={"access_token": at, "fmt": "json"}, timeout=10
        ).text
        openid = self._parse_openid(me_text)
        params = {
            "access_token": at,
            "oauth_consumer_key": self.client_id,
            "openid": openid,
        }
        data = requests.get(self.userinfo_url, params=params, timeout=10).json()
        return Identity(
            provider_user_id=openid,
            email=None,
            nickname=data.get("nickname") or "",
            avatar=data.get("figureurl_qq_2") or data.get("figureurl_qq_1") or "",
        )

    @staticmethod
    def _parse_openid(text: str) -> str:
        text = text.strip()
        if text.startswith("callback("):
            j = text[text.index("{") : text.rindex("}") + 1]
            return json.loads(j)["openid"]
        return json.loads(text)["openid"]


def is_provider_configured(name: str) -> bool:
    """True only when BOTH client_id and client_secret are present for `name`.

    Lets the login view fail fast with a clear error instead of silently
    bouncing the user to the provider with a bogus client_id (which just yields
    a confusing "client_id invalid" page on the provider side).
    """
    cfg = settings.OAUTH_PROVIDERS.get(name)
    if not cfg:
        return False
    return bool(cfg.get("client_id")) and bool(cfg.get("client_secret"))


_PROVIDER_CLIENT_ID_ENV = {
    "github": "GITHUB_CLIENT_ID",
    "wechat": "WECHAT_CLIENT_ID",
    "qq": "QQ_CLIENT_ID",
}


def configured_provider_env_var(name: str) -> str:
    """The env var a developer should set to configure `name`."""
    return _PROVIDER_CLIENT_ID_ENV.get(name, f"{name.upper()}_CLIENT_ID")


REGISTRY = {
    "github": GitHubProvider,
    "wechat": WeChatProvider,
    "qq": QQProvider,
}

# Human-readable labels for the account-binding UI (§9.2). Frontend may keep
# its own map, but returning them server-side keeps one source of truth.
PROVIDER_LABELS = {
    "github": "GitHub",
    "wechat": "微信",
    "qq": "QQ",
}


def default_redirect_uri(provider: str) -> str:
    base = settings.PASSPORT_OAUTH_REDIRECT_BASE.rstrip("/")
    uri = f"{base}/{provider}/callback/"
    # QQ 互联（腾讯开放平台）的回调地址校验器拒绝以 "/" 结尾的 URL，
    # 因此对 qq 去掉尾斜杠以通过控制台校验；Django 侧已同时接受带/不带斜杠。
    if provider == "qq":
        uri = uri.rstrip("/")
    return uri


def get_provider(name: str, redirect_uri: str | None = None) -> BaseProvider | None:
    cfg = settings.OAUTH_PROVIDERS.get(name)
    cls = REGISTRY.get(name)
    if not cfg or not cls:
        return None
    return cls(
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        redirect_uri=redirect_uri or default_redirect_uri(name),
    )
