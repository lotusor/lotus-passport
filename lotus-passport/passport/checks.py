"""
Production safety system checks.

These are WARNINGS (not errors) so `manage.py check` still exits 0 — they exist
to surface insecure defaults that would otherwise sail through a deployment.
They only fire when DEBUG=False (dev is allowed to use the placeholders).
"""
from django.conf import settings
from django.core.checks import Warning, register

_INSECURE_SECRET = "dev-insecure-secret-change-me-in-production"
_INSECURE_ENC_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


@register()
def check_production_secrets(app_configs, **kwargs):
    if getattr(settings, "DEBUG", False):
        return []

    errors = []
    if getattr(settings, "SECRET_KEY", "") == _INSECURE_SECRET:
        errors.append(
            Warning(
                "SECRET_KEY 仍是开发默认值，生产环境必须更换，否则会话/签名可被伪造。",
                id="passport.W001",
            )
        )
    if getattr(settings, "TOKEN_ENCRYPTION_KEY", "") == _INSECURE_ENC_KEY:
        errors.append(
            Warning(
                "TOKEN_ENCRYPTION_KEY 仍是开发默认值，第三方 OAuth 令牌可被解密。",
                id="passport.W002",
            )
        )
    hosts = getattr(settings, "ALLOWED_HOSTS", [])
    if not hosts or "*" in hosts:
        errors.append(
            Warning(
                "ALLOWED_HOSTS 为空或含 '*'，生产环境存在 Host 头攻击 / 密码重置投毒风险。",
                id="passport.W003",
            )
        )
    return errors
