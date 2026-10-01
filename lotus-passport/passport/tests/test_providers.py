"""Tests for the three OAuth providers (GitHub / WeChat / QQ).

Network is fully mocked; we only assert normalization into `Identity` and the
authorize-URL shape. The storage/encryption path is covered in test_oauth_flow.
"""
import json
from unittest.mock import MagicMock, patch

from passport.providers import GitHubProvider, QQProvider, WeChatProvider


class _Resp:
    """`requests.Response` 的最小替身：`.json()` 按真实语义去解 `.text`。

    用 MagicMock 当响应是个陷阱——`mock.json()` 不抛异常而是返回另一个 mock，
    于是 QQ「先试 JSON、失败再 parse_qsl」的兜底分支永远走不到，测试拿到的是
    MagicMock 而不是解析结果。真实 requests 不看 Content-Type，直接解码 body，
    解不动抛 ValueError（QQ 既会回 text/html 的 JSON，也会回 urlencoded）。
    """

    def __init__(self, text: str, headers: dict | None = None):
        self.text = text
        self.headers = headers or {}

    def json(self):
        return json.loads(self.text)


def _mock_session(token: dict):
    sess = MagicMock()
    sess.fetch_token.return_value = token
    return sess


def test_github_authorize_url_shape():
    p = GitHubProvider("cid", "csec", "https://cb.example.com/gh/cb")
    url = p.get_authorize_url("st4te")
    assert "github.com/login/oauth/authorize" in url
    assert "client_id=cid" in url
    assert "state=st4te" in url
    assert "scope=read%3Auser+user%3Aemail" in url or "scope=read:user user:email" in url


@patch("passport.providers.OAuth2Session")
def test_github_exchange_and_identity(mock_oauth):
    mock_oauth.return_value = _mock_session(
        {"access_token": "gh_at", "expires_in": 3600}
    )
    with patch("passport.providers.requests.get") as mget:
        mget.side_effect = [
            MagicMock(json=lambda: {"id": 12345, "login": "neo", "avatar_url": "https://a", "name": "Neo"}),
            MagicMock(json=lambda: [{"email": "neo@x.com", "primary": True, "verified": True}]),
        ]
        p = GitHubProvider("cid", "csec", "https://cb")
        token, exp = p.exchange_code("code")
        ident = p.fetch_identity(token)

    assert ident.provider_user_id == "12345"
    assert ident.email == "neo@x.com"
    assert ident.nickname == "neo"
    assert exp is not None


@patch("passport.providers.OAuth2Session")
def test_github_ignores_unverified_public_email(mock_oauth):
    """/user 的公开 email 可以是未验证的任意地址 → 只能信 /user/emails 的 verified 位。

    攻击者可以把 GitHub 公开邮箱填成受害者的地址；若拿它当身份，passport 就会
    把登录者当成受害者（历史版本会按邮箱命中已有账号）。
    """
    mock_oauth.return_value = _mock_session({"access_token": "gh_at", "expires_in": 3600})
    with patch("passport.providers.requests.get") as mget:
        mget.side_effect = [
            MagicMock(json=lambda: {
                "id": 777, "login": "attacker", "avatar_url": "https://a",
                "email": "victim@corp.com",          # 未验证的冒名地址
            }),
            MagicMock(json=lambda: [
                {"email": "victim@corp.com", "primary": True, "verified": False},
                {"email": "attacker@own.dev", "primary": False, "verified": True},
            ]),
        ]
        p = GitHubProvider("cid", "csec", "https://cb")
        token, _ = p.exchange_code("code")
        ident = p.fetch_identity(token)

    assert ident.email == "attacker@own.dev"          # 只取 verified 的那条
    assert ident.nickname == "attacker"


@patch("passport.providers.OAuth2Session")
def test_github_email_none_when_nothing_verified(mock_oauth):
    mock_oauth.return_value = _mock_session({"access_token": "gh_at", "expires_in": 3600})
    with patch("passport.providers.requests.get") as mget:
        mget.side_effect = [
            MagicMock(json=lambda: {"id": 778, "login": "x", "email": "who@ever.com"}),
            MagicMock(json=lambda: [{"email": "who@ever.com", "primary": True,
                                     "verified": False}]),
        ]
        p = GitHubProvider("cid", "csec", "https://cb")
        token, _ = p.exchange_code("code")
        ident = p.fetch_identity(token)

    assert ident.email is None


@patch("passport.providers.OAuth2Session")
def test_github_email_none_when_emails_endpoint_errors(mock_oauth):
    """邮箱接口挂了要 fail closed（None），不能退回用公开字段。"""
    mock_oauth.return_value = _mock_session({"access_token": "gh_at", "expires_in": 3600})
    with patch("passport.providers.requests.get") as mget:
        mget.side_effect = [
            MagicMock(json=lambda: {"id": 779, "login": "x", "email": "who@ever.com"}),
            MagicMock(json=lambda: {"message": "Bad credentials", "documentation_url": "…"}),
        ]
        p = GitHubProvider("cid", "csec", "https://cb")
        token, _ = p.exchange_code("code")
        ident = p.fetch_identity(token)

    assert ident.email is None


@patch("passport.providers.OAuth2Session")
def test_wechat_identity_prefers_unionid(mock_oauth):
    mock_oauth.return_value = _mock_session(
        {"access_token": "wx_at", "openid": "o123", "unionid": "u123", "expires_in": 7200}
    )
    with patch("passport.providers.requests.get") as mget:
        mget.return_value = MagicMock(json=lambda: {"nickname": "微信用户", "headimgurl": "https://wx"})
        p = WeChatProvider("cid", "csec", "https://cb")
        token, _ = p.exchange_code("code")
        ident = p.fetch_identity(token)

    assert ident.provider_user_id == "u123"  # unionid wins over openid
    assert ident.nickname == "微信用户"
    assert ident.email is None


def test_qq_exchange_and_identity_urlencoded():
    with patch("passport.providers.requests.post") as mpost, patch(
        "passport.providers.requests.get"
    ) as mget:
        mpost.return_value = _Resp(
            "access_token=qq_at&expires_in=3600", {"Content-Type": "text/html"})
        mget.side_effect = [
            MagicMock(text='callback( {"openid":"QQOPENID"} );'),
            MagicMock(json=lambda: {"nickname": "QQ用户", "figureurl_qq_2": "https://qq"}),
        ]
        p = QQProvider("cid", "csec", "https://cb")
        token, _ = p.exchange_code("code")
        ident = p.fetch_identity(token)

    assert ident.provider_user_id == "QQOPENID"
    assert ident.nickname == "QQ用户"
    assert token["access_token"] == "qq_at"


def test_qq_exchange_json_with_text_html_content_type():
    """QQ returns JSON (fmt=json) but ships Content-Type: text/html — the real
    cause of the original 'access_token' 502. JSON must win over parse_qsl."""
    with patch("passport.providers.requests.post") as mpost, patch(
        "passport.providers.requests.get"
    ) as mget:
        mpost.return_value = _Resp(
            '{"access_token":"qq_at","expires_in":3600,"refresh_token":"r"}',
            {"Content-Type": "text/html;charset=utf-8"})
        mget.side_effect = [
            MagicMock(text='callback( {"openid":"QQOPENID"} );'),
            MagicMock(json=lambda: {"nickname": "QQ用户", "figureurl_qq_2": "https://qq"}),
        ]
        p = QQProvider("cid", "csec", "https://cb")
        token, _ = p.exchange_code("code")
        ident = p.fetch_identity(token)

    assert token["access_token"] == "qq_at"
    assert ident.provider_user_id == "QQOPENID"


def test_qq_parse_openid_json():
    assert QQProvider._parse_openid('{"openid":"X"}') == "X"
    assert QQProvider._parse_openid('callback( {"openid":"Y"} );') == "Y"


def test_qq_exchange_raises_on_error_json():
    """QQ error JSON must surface the real reason, not a KeyError 502."""
    with patch("passport.providers.requests.post") as mpost:
        mpost.return_value = _Resp(
            '{"error": 100007, "error_description": "client_secret error"}',
            {"Content-Type": "application/json"})
        p = QQProvider("cid", "csec", "https://cb")
        try:
            p.exchange_code("code")
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "client_secret error" in str(exc)


def test_qq_exchange_raises_on_error_urlencoded():
    """QQ error urlencoded body must also be detected."""
    with patch("passport.providers.requests.post") as mpost:
        mpost.return_value = _Resp(
            "error=100007&error_description=client_secret error",
            {"Content-Type": "text/html"})
        p = QQProvider("cid", "csec", "https://cb")
        try:
            p.exchange_code("code")
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "client_secret error" in str(exc)


def test_qq_fetch_identity_raises_without_access_token():
    p = QQProvider("cid", "csec", "https://cb")
    try:
        p.fetch_identity({"openid": "X"})  # no access_token key
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "access_token" in str(exc)
