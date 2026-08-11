"""Django REST Framework adapter.

Settings::

    LOTUS_PASSPORT = {
        "BASE_URL": "https://passport.eacm.cn",
        "ISSUER": "lotus-passport",
        # Optional dotted path to your own resolver:
        # "USER_RESOLVER": "myapp.auth.resolve_passport_user",
        "AUTO_CREATE_USER": True,
    }

    REST_FRAMEWORK = {
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "lotus_passport.integrations.drf.PassportAuthentication",
        ],
    }

The identity is attached to ``request.auth`` so views can read
``request.auth.passport_user_id`` without re-decoding the token.
"""
from __future__ import annotations

from typing import Any, Callable

from ..client import PassportClient
from ..errors import PassportServiceError, TokenError, TokenExpired
from ..types import PassportIdentity

_client: PassportClient | None = None


def get_client() -> PassportClient:
    """Return the process-wide client, built from ``settings.LOTUS_PASSPORT``.

    Cached deliberately: a fresh client per request would mean a fresh (empty)
    JWKS cache per request, i.e. a JWKS fetch on every single API call.

    Raises:
        ImproperlyConfigured: ``LOTUS_PASSPORT["BASE_URL"]`` is missing.
    """
    global _client
    if _client is not None:
        return _client

    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    conf: dict[str, Any] = getattr(settings, "LOTUS_PASSPORT", {}) or {}
    base_url = conf.get("BASE_URL")
    if not base_url:
        raise ImproperlyConfigured(
            "LOTUS_PASSPORT['BASE_URL'] is required, e.g. https://passport.eacm.cn"
        )

    _client = PassportClient(
        base_url,
        issuer=conf.get("ISSUER", "lotus-passport"),
        audience=conf.get("AUDIENCE"),
        leeway=conf.get("LEEWAY", 30),
        cache_ttl=conf.get("JWKS_CACHE_TTL", 600.0),
        timeout=conf.get("TIMEOUT", 5.0),
    )
    return _client


def reset_client() -> None:
    """Drop the cached client (tests / settings reload)."""
    global _client
    _client = None


def _load_resolver() -> Callable[[PassportIdentity], Any] | None:
    from django.conf import settings
    from django.utils.module_loading import import_string

    conf = getattr(settings, "LOTUS_PASSPORT", {}) or {}
    path = conf.get("USER_RESOLVER")
    return import_string(path) if path else None


def default_user_resolver(identity: PassportIdentity) -> Any:
    """Map an identity onto a local Django user.

    Resolution order:

    1. If your user model has a ``passport_user_id`` field, match on it. **This
       is the right way** — it survives email and nickname changes.
    2. Otherwise fall back to ``USERNAME_FIELD == passport_user_id``, which keeps
       the SDK usable against a stock ``auth.User`` without a migration.

    ``AUTO_CREATE_USER=False`` turns a first-time visitor into an auth failure
    instead of provisioning a row — useful for invite-only services.

    Returns:
        The local user instance, or ``None`` when auto-creation is disabled and
        no local row exists.
    """
    from django.conf import settings
    from django.contrib.auth import get_user_model

    conf = getattr(settings, "LOTUS_PASSPORT", {}) or {}
    auto_create = conf.get("AUTO_CREATE_USER", True)
    User = get_user_model()
    pid = identity.passport_user_id

    field_names = {f.name for f in User._meta.get_fields() if hasattr(f, "name")}
    if "passport_user_id" in field_names:
        lookup = {"passport_user_id": pid}
    else:
        lookup = {User.USERNAME_FIELD: pid}

    user = User.objects.filter(**lookup).first()
    if user is not None:
        return user
    if not auto_create:
        return None

    create_kwargs = dict(lookup)
    if "email" in field_names and identity.email:
        create_kwargs["email"] = identity.email
    # A passport-backed account has no local password; an unusable one blocks
    # password login outright rather than leaving an empty-string hash.
    user = User(**create_kwargs)
    if hasattr(user, "set_unusable_password"):
        user.set_unusable_password()
    user.save()
    return user


class PassportAuthentication:
    """DRF authentication backed by Lotus Passport RS256 tokens.

    Implements the ``BaseAuthentication`` interface without importing DRF at
    module import time, so this file stays importable in a non-DRF process
    (e.g. a management command that only needs ``get_client()``).
    """

    keyword = "Bearer"

    def authenticate(self, request: Any):  # noqa: ANN401 - DRF signature
        from rest_framework import exceptions

        header = request.META.get("HTTP_AUTHORIZATION")
        client = get_client()
        token = client.extract_bearer(header)
        if token is None:
            return None  # let other authenticators try; DRF turns this into 401

        try:
            identity = client.verify_token(token)
        except TokenExpired as exc:
            raise exceptions.AuthenticationFailed("访问令牌已过期，请刷新") from exc
        except TokenError as exc:
            raise exceptions.AuthenticationFailed(f"令牌无效: {exc}") from exc
        except PassportServiceError as exc:
            # 503, not 401 — the credential may well be fine.
            raise exceptions.APIException(f"认证中心暂时不可用: {exc}") from exc

        resolver = _load_resolver() or default_user_resolver
        user = resolver(identity)
        if user is None:
            raise exceptions.AuthenticationFailed("本系统尚未开通该通行证账号")
        return (user, identity)

    def authenticate_header(self, request: Any) -> str:  # noqa: ANN401
        return self.keyword


__all__ = [
    "PassportAuthentication",
    "get_client",
    "reset_client",
    "default_user_resolver",
]
