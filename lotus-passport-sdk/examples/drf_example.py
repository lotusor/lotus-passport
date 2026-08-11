"""Minimal Django REST Framework app protected by Lotus Passport (RS256 JWT).

This is a STANDALONE runnable module: it calls ``settings.configure()`` so you can
run it without a full Django project tree. In a real project you would instead put
``LOTUS_PASSPORT`` and the ``DEFAULT_AUTHENTICATION_CLASSES`` entry in your
``settings.py`` (see lotus-passport-sdk/README.md § DRF).

What the adapter gives you:
- Every request with a Bearer token is verified offline against the JWKS cache.
- ``request.auth`` becomes a verified ``PassportIdentity`` (no re-decoding).
- A resolver maps the identity onto a local user. By default it matches a
  ``passport_user_id`` field, and auto-creates the local row on first sight.

Run (from the repo root):

    uv run --extra drf python examples/drf_example.py

The script boots a test client and proves the wiring rejects anonymous requests
with 401 and (given a real token) resolves a local user.
"""
from __future__ import annotations

import django
from django.conf import settings
from django.urls import path

PASSPORT_BASE_URL = "https://passport.eacm.cn"


def configure_settings() -> None:
    settings.configure(
        DEBUG=True,
        SECRET_KEY="example-only-not-a-real-secret",
        DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
        },
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "rest_framework",
        ],
        LOTUS_PASSPORT={
            "BASE_URL": PASSPORT_BASE_URL,
            "ISSUER": "lotus-passport",
            "AUTO_CREATE_USER": True,  # provision a local row on first sight
            # "USER_RESOLVER": "myapp.auth.resolve_passport_user",  # optional override
        },
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "lotus_passport.integrations.drf.PassportAuthentication",
            ],
        },
        # This example is a single script: route /me to the view via __main__.
        # In a real project point this at your urls.py instead.
        ROOT_URLCONF=__name__,
    )
    django.setup()


configure_settings()

from django.test import Client  # noqa: E402
from rest_framework.decorators import api_view, permission_classes  # noqa: E402
from rest_framework.permissions import IsAuthenticated  # noqa: E402
from rest_framework.response import Response  # noqa: E402


@api_view(["GET"])
@permission_classes([IsAuthenticated])  # anonymous -> 401; valid token -> identity
def me(request) -> Response:
    identity = request.auth  # a verified PassportIdentity
    return Response(
        {
            "passport_user_id": identity.passport_user_id,
            "email": identity.email,
            "source": identity.source,
        }
    )


# Wire the view into the URLconf referenced by ROOT_URLCONF above.
urlpatterns = [path("me/", me)]


if __name__ == "__main__":
    # Prove the integration boots and rejects an anonymous call with 401.
    # (Supplying a valid passport token here would additionally exercise the
    # resolver; mint one with the passport dev login — README §2.2.)
    client = Client()
    resp = client.get("/me/")
    print(f"GET /me/ (no token) -> HTTP {resp.status_code}")  # expect 401
    assert resp.status_code == 401, "anonymous request must be rejected"
    print("OK: DRF integration wired correctly.")
