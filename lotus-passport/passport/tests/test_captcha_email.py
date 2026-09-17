"""CAPTCHA gate on the email-code send endpoint (邮件轰炸 / SMTP 配额防护).

The gate is adaptive: send-code requests are counted per source IP and per
target address inside a fixed window, and a CAPTCHA token only becomes
mandatory once either dimension crosses its threshold. These tests pin down:

* the gate is inert unless both ``CAPTCHA_ENABLED`` and
  ``CAPTCHA_EMAIL_ENABLED`` are on (so it can be rolled back independently of
  the login CAPTCHA, and so the default suite is unaffected);
* both dimensions trip independently;
* a missing token blocks the send without consuming a code;
* a solved token clears the *address* counter but deliberately NOT the IP
  counter (clearing IP would hand an attacker a fresh batch of free sends).
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient

from passport.models import PassportUser
from passport.ratelimit import CaptchaGate

pytestmark = pytest.mark.django_db

SEND_URL = "/api/v1/security/email/send-code/"
ADDR_THRESHOLD = 3
IP_THRESHOLD = 10


@pytest.fixture
def captcha_on(settings):
    """SMTP enabled + CAPTCHA fully enabled (both switches)."""
    settings.PASSWORD_RESET_ENABLED = True
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.HCAPTCHA_SECRET_KEY = "test-secret"
    settings.CAPTCHA_ENABLED = True
    settings.CAPTCHA_EMAIL_ENABLED = True
    settings.CAPTCHA_EMAIL_IP_THRESHOLD = IP_THRESHOLD
    settings.CAPTCHA_EMAIL_ADDR_THRESHOLD = ADDR_THRESHOLD
    settings.CAPTCHA_EMAIL_WINDOW = 3600
    return settings


def _send(c, email, captcha=None):
    body = {"email": email, "purpose": "login"}
    if captcha:
        body["captcha"] = captcha
    return c.post(SEND_URL, body, format="json")


def _solve(c, email):
    """Send with a token the mocked hCaptcha endpoint accepts."""
    with patch("passport.captcha.requests.post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"success": True})
        return _send(c, email, captcha="tok")


def _code(r):
    """Error code, or None when the response is a success (no `error` key)."""
    try:
        return r.json().get("error", {}).get("code")
    except Exception:  # noqa: BLE001 — non-JSON body
        return None


# --- 开关语义 ---------------------------------------------------------------- #
def test_gate_inert_when_captcha_disabled(captcha_on):
    """CAPTCHA_ENABLED=False → 完全不走门禁，连续发码不被拦。"""
    captcha_on.CAPTCHA_ENABLED = False
    c = APIClient()
    for _ in range(ADDR_THRESHOLD + 1):
        assert _code(_send(c, "a@example.com")) != "captcha_required"


def test_gate_inert_when_email_flag_off(captcha_on):
    """CAPTCHA_EMAIL_ENABLED=False → 邮箱侧单独回滚，不影响登录验证码。"""
    captcha_on.CAPTCHA_EMAIL_ENABLED = False
    c = APIClient()
    for _ in range(ADDR_THRESHOLD + 1):
        assert _code(_send(c, "b@example.com")) != "captcha_required"


@override_settings(HCAPTCHA_SECRET_KEY="", CAPTCHA_ENABLED=False)
def test_gate_inert_without_secret(settings):
    """未配置 hCaptcha secret 的环境（部署前默认状态）门禁完全不生效。

    注意：本地 .env 带真实 HCAPTCHA_SECRET_KEY，所以测试环境里 CAPTCHA 默认
    是开的——要验证「关」必须显式清掉 secret。
    """
    settings.PASSWORD_RESET_ENABLED = True
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    c = APIClient()
    for _ in range(ADDR_THRESHOLD + 1):
        assert _code(_send(c, "nosecret@example.com")) != "captcha_required"


def test_single_send_is_unaffected(captcha_on):
    """回归保护：正常用户发一次码不会被要求验证码。"""
    c = APIClient()
    r = _send(c, "normal@example.com")
    assert r.status_code == 200
    assert _code(r) is None


# --- 触发：邮箱维度 ----------------------------------------------------------- #
def test_address_dimension_trips(captcha_on):
    """同一邮箱第 4 次请求被要求验证码（前 3 次仅受 60s 冷却限制）。"""
    c = APIClient()
    assert _send(c, "victim@example.com").status_code == 200

    # 第 2、3 次被 60s 冷却拒绝，但门禁计数照记（脚本猛打会更快触发）
    for _ in range(ADDR_THRESHOLD - 1):
        r = _send(c, "victim@example.com")
        assert r.status_code == 429
        assert r.json()["error"]["code"] != "captcha_required"

    # 第 4 次：地址维度计数已达 3 → 要求验证码
    r = _send(c, "victim@example.com")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "captcha_required"
    # 前端 ApiException 读的是这个字段（与密码登录 401 分支保持一致）
    assert r.json()["error"]["captcha_required"] is True


def test_missing_token_does_not_send_mail(captcha_on):
    """被门禁拦下时不发信 —— 这才是防轰炸的实际收益。"""
    c = APIClient()
    _send(c, "nomail@example.com")
    before = len(mail.outbox)
    for _ in range(ADDR_THRESHOLD):
        _send(c, "nomail@example.com")
    r = _send(c, "nomail@example.com")
    assert r.json()["error"]["code"] == "captcha_required"
    assert len(mail.outbox) == before


# --- 触发：IP 维度 ------------------------------------------------------------ #
def test_ip_dimension_trips(captcha_on):
    """同一 IP 打不同邮箱：地址维度各自只有 1 次，靠 IP 维度触发。"""
    c = APIClient()
    for i in range(IP_THRESHOLD):
        r = _send(c, f"many{i}@example.com")
        assert r.status_code == 200, r.json()

    r = _send(c, "one-too-many@example.com")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "captcha_required"


# --- token 校验 -------------------------------------------------------------- #
def test_invalid_token_rejected(captcha_on):
    c = APIClient()
    for _ in range(ADDR_THRESHOLD):
        _send(c, "bad@example.com")

    with patch("passport.captcha.requests.post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"success": False})
        r = _send(c, "bad@example.com", captcha="tok")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "captcha_invalid"

    # 计数未被清零 → 仍然要求验证码
    r = _send(c, "bad@example.com")
    assert r.json()["error"]["code"] == "captcha_required"


def test_valid_token_sends_mail(captcha_on):
    """IP 维度触发后，带有效 token 的请求正常放行并发信。"""
    c = APIClient()
    for i in range(IP_THRESHOLD):
        assert _send(c, f"trip{i}@example.com").status_code == 200

    before = len(mail.outbox)
    # 全新邮箱 → 不撞 60s 冷却，能干净地观察到「通过后真的发信了」
    r = _solve(c, "solved@example.com")
    assert r.status_code == 200
    assert len(mail.outbox) == before + 1


def test_valid_token_clears_address_counter(captcha_on):
    """地址维度触发 → 解掉后该邮箱不再被要求验证码（只会撞 60s 冷却）。

    门禁检查位于冷却之前，所以解完验证码仍会 429——关键是错误码不再是
    captcha_required，证明地址计数确实被清零了。
    """
    c = APIClient()
    for _ in range(ADDR_THRESHOLD):
        _send(c, "clear-me@example.com")
    assert _code(_send(c, "clear-me@example.com")) == "captcha_required"

    r = _solve(c, "clear-me@example.com")
    assert _code(r) != "captcha_required"
    assert r.status_code == 429  # 是冷却，不是验证码


def test_valid_token_does_not_clear_ip_counter(captcha_on):
    """关键设计：解一次验证码不该让攻击者白拿一批发送额度。"""
    c = APIClient()
    for i in range(IP_THRESHOLD):
        assert _send(c, f"trip{i}@example.com").status_code == 200

    # 第 11 次被 IP 维度拦下，用有效 token 解掉
    assert _send(c, "trip10@example.com").json()["error"]["code"] == "captcha_required"
    assert _solve(c, "trip10@example.com").status_code == 200

    # IP 计数没有被清零 → 换一个新邮箱仍然要求验证码
    r = _send(c, "fresh@example.com")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "captcha_required"


# --- CaptchaGate 单元行为 ----------------------------------------------------- #
def test_gate_unit_semantics(captcha_on):
    gate = CaptchaGate()
    ip, email = "203.0.113.9", "unit@example.com"

    assert gate.required(ip, email) is False

    for _ in range(ADDR_THRESHOLD):
        gate.touch(ip, email)
    assert gate.required(ip, email) is True

    gate.clear(email)
    assert gate.required(ip, email) is False  # 地址维度已清零
    assert gate._count(gate._ip_key(ip)) == ADDR_THRESHOLD  # IP 维度保留


def test_gate_counters_expire(captcha_on):
    """计数带 TTL，窗口过后自动失效（不会永久卡住用户）。"""
    captcha_on.CAPTCHA_EMAIL_WINDOW = 1
    gate = CaptchaGate()
    ip, email = "203.0.113.10", "ttl@example.com"
    for _ in range(ADDR_THRESHOLD):
        gate.touch(ip, email)
    assert gate.required(ip, email) is True

    import time

    time.sleep(1.2)
    assert gate.required(ip, email) is False


def test_gate_degrades_when_redis_fails(captcha_on):
    """Redis 故障时降级为「不要求验证码」，不阻断发信（可用性优先）。"""
    gate = CaptchaGate(client=MagicMock())
    gate.client.get.side_effect = RuntimeError("redis down")
    gate.client.incr.side_effect = RuntimeError("redis down")
    gate.client.delete.side_effect = RuntimeError("redis down")

    assert gate.required("203.0.113.11", "degraded@example.com") is False
    gate.touch("203.0.113.11", "degraded@example.com")  # 不抛异常
    gate.clear("degraded@example.com")  # 不抛异常
