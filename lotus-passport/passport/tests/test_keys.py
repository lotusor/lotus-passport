"""KeyStore rotation + kid-aware verification + multi-key JWKS tests."""
import tempfile

import jwt as pyjwt
import pytest
from django.conf import settings
from django.test import Client

from passport.keys import KeyStore


def _make_token(private_pem: str, kid: str, ttl: int = 3600) -> str:
    import time

    return pyjwt.encode(
        {"sub": "1", "exp": int(time.time()) + ttl},
        private_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )


@pytest.fixture
def store(monkeypatch):
    d = tempfile.mkdtemp()
    ks = KeyStore(d, initial_kid="kid-1")
    ks.ensure_initial(kid="kid-1")
    monkeypatch.setattr(settings, "KEY_STORE", ks)
    return ks


def _backend(ks: KeyStore):
    from passport.jwt import PassportTokenBackend

    return PassportTokenBackend(
        algorithm="RS256",
        signing_key=ks.active_private_pem,
        verifying_key=ks.active_public_pem,
    )


def test_initial_key_written(store):
    import os

    assert os.path.exists(os.path.join(store.keys_dir, "manifest.json"))
    assert store.active_kid == "kid-1"
    # JWKS for a single (initial) key.
    assert len(store.all_public()) == 1


def test_rotation_keeps_old_token_valid(store):
    backend = _backend(store)
    old = _make_token(store.active_private_pem, "kid-1")

    # Old token verifies before rotation.
    assert backend.decode(old)

    new_kid = store.rotate(retention_days=16)
    assert new_kid != "kid-1"
    assert store.active_kid == new_kid

    backend2 = _backend(store)
    # Old token still verifies (kid-1 retained during overlap window).
    assert backend2.decode(old)
    # New token verifies.
    new = _make_token(store.active_private_pem, new_kid)
    assert backend2.decode(new)
    # JWKS publishes both keys.
    assert len(store.all_public()) == 2


def test_rotation_prunes_expired_keys(store):
    old = _make_token(store.active_private_pem, "kid-1")
    backend = _backend(store)

    # retention_days=0 -> the previous key is immediately pruned.
    store.rotate(retention_days=0)
    assert [k for k, _ in store.all_public()] == [store.active_kid]
    assert store.active_kid != "kid-1"
    # The old token can no longer be verified (key gone).
    with pytest.raises(Exception):
        backend.decode(old)


@pytest.mark.django_db(transaction=True)
def test_jwks_publishes_multiple_keys(store, client):
    new_kid = store.rotate(retention_days=16)
    r = client.get("/.well-known/jwks.json")
    assert r.status_code == 200
    keys = r.json()["keys"]
    assert len(keys) == 2
    assert {k["kid"] for k in keys} == {"kid-1", new_kid}
    # Every published key carries the RS256 fields.
    for k in keys:
        assert k["kty"] == "RSA" and k["alg"] == "RS256" and "n" in k and "e" in k


@pytest.mark.django_db(transaction=True)
def test_generate_keys_command_writes_manifest(monkeypatch):
    import os

    from django.core.management import call_command

    d = tempfile.mkdtemp()
    ks = KeyStore(d, initial_kid="gen-kid")
    monkeypatch.setattr(settings, "KEY_STORE", ks)

    call_command("generate_keys")
    assert os.path.exists(os.path.join(d, "manifest.json"))
    assert ks.active_kid == settings.JWT_KID


@pytest.mark.django_db(transaction=True)
def test_rotate_keys_command_changes_active(monkeypatch):
    from django.core.management import call_command

    d = tempfile.mkdtemp()
    ks = KeyStore(d, initial_kid="rc-1")
    ks.ensure_initial(kid="rc-1")
    monkeypatch.setattr(settings, "KEY_STORE", ks)

    before = ks.active_kid
    call_command("rotate_keys", "--retention-days", "16")
    assert ks.active_kid != before
    assert len(ks.all_public()) == 2
