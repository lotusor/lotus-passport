"""Shared pytest fixtures for the passport test-suite."""
import pytest
from django.db.models.signals import post_save
from django.utils import timezone
from rest_framework.test import APIClient as _APIClient

from passport.auth_events import parse_user_agent
from passport.models import PassportUser, TrustedDevice
from passport.ratelimit import get_redis


# §9.3 trust gate (`IsAuthenticatedAndTrusted`) keys on the UA fingerprint, so
# every API call in the suite must carry one. Patch APIClient so any existing
# test that just does APIClient() / client.credentials(...) silently gets a UA
# matching the Edge/Windows device created by `_ensure_trusted_device`.
_TEST_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
)
_orig_init = _APIClient.__init__


def _patched_init(self, *args, **kwargs):
    _orig_init(self, *args, **kwargs)
    self.defaults.setdefault("HTTP_USER_AGENT", _TEST_UA)


_APIClient.__init__ = _patched_init


# Tests often authenticate via `force_authenticate(user=...)` (skipping JWT) or
# `client.credentials(Bearer ...)` (real token path). In both cases the gate's
# UA-fingerprint check still runs, so the test user must have a matching
# trusted=True TrustedDevice row. Auto-create one on user creation so existing
# tests don't have to change; the device lives only in the test DB (rolled
# back per test) and is idempotent (`get_or_create`).
def _auto_trust_on_create(sender, instance, created, **kwargs):
    if not created:
        return
    parsed = parse_user_agent(_TEST_UA)
    TrustedDevice.objects.get_or_create(
        user=instance,
        device_type=parsed["device_type"],
        os=parsed["os"],
        browser=parsed["browser"],
        defaults={
            "name": "test-device",
            "trusted": True,
            "first_trusted_at": timezone.now(),
        },
    )


post_save.connect(_auto_trust_on_create, sender=PassportUser)


@pytest.fixture(autouse=True)
def _flush_redis():
    """Keep the (fake)redis clean between tests so state/rate-limit don't leak."""
    r = get_redis()
    try:
        r.flushall()
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        r.flushall()
    except Exception:  # noqa: BLE001
        pass
