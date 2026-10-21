"""Django / DRF adapter, exercised against a real (in-memory) Django stack.

This is the adapter that matters most for us: algo_rank is Django + DRF, so a
regression here breaks the flagship integration. Django is booted with
``settings.configure()`` and an in-memory SQLite DB — no project, no files, and
crucially no journal files (this sandbox cannot delete them).
"""
from __future__ import annotations

import pytest

django = pytest.importorskip("django")
pytest.importorskip("rest_framework")

from django.conf import settings as dj_settings  # noqa: E402

from .conftest import ISSUER, FakeTransport, KeyPair  # noqa: E402

PASSPORT_ID = "11111111-1111-1111-1111-111111111111"


def _boot_django() -> None:
    if dj_settings.configured:
        return
    dj_settings.configure(
        DEBUG=True,
        SECRET_KEY="sdk-test-only",
        DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
        },
        INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth"],
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        USE_TZ=True,
        LOTUS_PASSPORT={"BASE_URL": "https://passport.test", "ISSUER": ISSUER},
    )
    django.setup()
    from django.core.management import call_command

    call_command("migrate", run_syncdb=True, verbosity=0)


@pytest.fixture(scope="module", autouse=True)
def django_stack():
    _boot_django()
    yield


@pytest.fixture(autouse=True)
def clean_users(django_stack):
    from django.contrib.auth import get_user_model

    get_user_model().objects.all().delete()
    yield


@pytest.fixture
def drf_client(transport: FakeTransport):
    """Install a client backed by the offline transport into the DRF adapter."""
    from lotus_passport import PassportClient
    from lotus_passport.integrations import drf

    drf.reset_client()
    drf._client = PassportClient(
        "https://passport.test", transport=transport, issuer=ISSUER
    )
    yield drf._client
    drf.reset_client()


class FakeRequest:
    def __init__(self, authorization: str | None = None) -> None:
        self.META = {}
        if authorization:
            self.META["HTTP_AUTHORIZATION"] = authorization


# --------------------------------------------------------------------------- #
# user resolution
# --------------------------------------------------------------------------- #
def test_default_resolver_creates_then_reuses_a_user(django_stack):
    from django.contrib.auth import get_user_model

    from lotus_passport.integrations.drf import default_user_resolver
    from lotus_passport.types import PassportIdentity

    identity = PassportIdentity(passport_user_id=PASSPORT_ID, email="a@b.c")

    first = default_user_resolver(identity)
    second = default_user_resolver(identity)

    assert first.pk == second.pk, "second login must not create a duplicate user"
    assert get_user_model().objects.count() == 1
    assert first.get_username() == PASSPORT_ID
    assert first.email == "a@b.c"
    assert not first.has_usable_password(), "passport accounts must not have a local password"


def test_auto_create_can_be_disabled(django_stack):
    from django.test import override_settings

    from lotus_passport.integrations.drf import default_user_resolver
    from lotus_passport.types import PassportIdentity

    identity = PassportIdentity(passport_user_id=PASSPORT_ID)
    conf = {"BASE_URL": "https://passport.test", "AUTO_CREATE_USER": False}
    with override_settings(LOTUS_PASSPORT=conf):
        assert default_user_resolver(identity) is None


# --------------------------------------------------------------------------- #
# authentication class
# --------------------------------------------------------------------------- #
def test_authenticate_returns_user_and_identity(drf_client, keypair: KeyPair):
    from lotus_passport.integrations.drf import PassportAuthentication

    result = PassportAuthentication().authenticate(
        FakeRequest(f"Bearer {keypair.sign()}")
    )

    assert result is not None
    user, identity = result
    assert identity.passport_user_id == PASSPORT_ID
    assert user.get_username() == PASSPORT_ID


def test_authenticate_returns_none_without_a_bearer_header(drf_client):
    from lotus_passport.integrations.drf import PassportAuthentication

    assert PassportAuthentication().authenticate(FakeRequest()) is None
    assert PassportAuthentication().authenticate(FakeRequest("Basic zzz")) is None


def test_authenticate_rejects_a_foreign_token(drf_client, rotated_keypair: KeyPair):
    from rest_framework import exceptions

    from lotus_passport.integrations.drf import PassportAuthentication

    with pytest.raises(exceptions.AuthenticationFailed):
        PassportAuthentication().authenticate(
            FakeRequest(f"Bearer {rotated_keypair.sign()}")
        )


def test_authenticate_reports_outage_as_503_not_401(
    drf_client, keypair: KeyPair, transport: FakeTransport
):
    """A passport outage must NOT look like a bad credential."""
    from rest_framework import exceptions

    from lotus_passport.integrations.drf import PassportAuthentication

    transport.fail_next_jwks = True
    with pytest.raises(exceptions.APIException) as err:
        PassportAuthentication().authenticate(FakeRequest(f"Bearer {keypair.sign()}"))
    assert not isinstance(err.value, exceptions.AuthenticationFailed)


def test_get_client_is_cached(django_stack):
    from lotus_passport.integrations import drf

    drf.reset_client()
    assert drf.get_client() is drf.get_client(), "a fresh client per request = JWKS per request"
    drf.reset_client()
