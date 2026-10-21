"""JWKS cache behaviour — the part that decides whether you DoS your auth server."""
from __future__ import annotations

import pytest

from lotus_passport import JWKSCache
from lotus_passport.errors import JWKSError, UnknownSigningKey

from .conftest import DEFAULT_KID, FakeTransport, KeyPair


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_cache(transport: FakeTransport, clock: FakeClock, **kwargs) -> JWKSCache:
    return JWKSCache(
        "https://passport.test/.well-known/jwks.json", transport, clock=clock, **kwargs
    )


def test_first_lookup_fetches_once_then_caches(transport: FakeTransport):
    clock = FakeClock()
    cache = make_cache(transport, clock, ttl=600)

    for _ in range(5):
        assert cache.get_key(DEFAULT_KID) is not None

    assert transport.jwks_fetches == 1, "cache must not refetch on every verification"


def test_refetches_after_ttl(transport: FakeTransport):
    clock = FakeClock()
    cache = make_cache(transport, clock, ttl=60)

    cache.get_key(DEFAULT_KID)
    clock.advance(61)
    cache.get_key(DEFAULT_KID)

    assert transport.jwks_fetches == 2


def test_unknown_kid_triggers_one_refresh_then_raises(transport: FakeTransport):
    clock = FakeClock()
    cache = make_cache(transport, clock, ttl=600, min_refresh_interval=0)

    with pytest.raises(UnknownSigningKey) as err:
        cache.get_key("no-such-kid")

    assert "no-such-kid" in str(err.value)
    # one TTL-miss fetch + one forced refresh, and no more
    assert transport.jwks_fetches == 2


def test_forced_refresh_is_throttled(transport: FakeTransport):
    """A flood of tokens with random kids must not become a JWKS flood."""
    clock = FakeClock()
    cache = make_cache(transport, clock, ttl=600, min_refresh_interval=30)
    cache.get_key(DEFAULT_KID)  # warm: 1 fetch
    baseline = transport.jwks_fetches

    for i in range(50):
        with pytest.raises(UnknownSigningKey):
            cache.get_key(f"forged-{i}")

    assert transport.jwks_fetches - baseline <= 1, "throttle failed — attacker can amplify"


def test_key_rotation_is_picked_up_without_restart(
    transport: FakeTransport, keypair: KeyPair, rotated_keypair: KeyPair
):
    clock = FakeClock()
    cache = make_cache(transport, clock, ttl=600, min_refresh_interval=0)
    cache.get_key(DEFAULT_KID)

    transport.jwks_response = (200, {"keys": [keypair.jwk(), rotated_keypair.jwk()]})
    assert cache.get_key(rotated_keypair.kid) is not None
    assert set(cache.key_ids()) == {DEFAULT_KID, rotated_keypair.kid}


def test_warm_cache_survives_a_passport_outage(transport: FakeTransport):
    """A blip must not invalidate every session."""
    clock = FakeClock()
    cache = make_cache(transport, clock, ttl=60)
    cache.get_key(DEFAULT_KID)

    clock.advance(61)
    transport.fail_next_jwks = True
    assert cache.get_key(DEFAULT_KID) is not None  # served from the stale-but-warm cache


def test_cold_cache_outage_raises_jwks_error(transport: FakeTransport):
    clock = FakeClock()
    cache = make_cache(transport, clock)
    transport.fail_next_jwks = True

    with pytest.raises(JWKSError):
        cache.get_key(DEFAULT_KID)


def test_non_200_jwks_raises(transport: FakeTransport):
    clock = FakeClock()
    transport.jwks_response = (503, None)
    cache = make_cache(transport, clock)

    with pytest.raises(JWKSError) as err:
        cache.get_key(DEFAULT_KID)
    assert err.value.status_code == 503


def test_symmetric_keys_in_jwks_are_ignored(transport: FakeTransport, keypair: KeyPair):
    """An `oct` key in a *public* document is either a mistake or an attack."""
    clock = FakeClock()
    transport.jwks_response = (
        200,
        {
            "keys": [
                {"kty": "oct", "kid": "sneaky", "k": "c2VjcmV0", "alg": "HS256"},
                keypair.jwk(),
            ]
        },
    )
    cache = make_cache(transport, clock, min_refresh_interval=0)

    assert cache.get_key(DEFAULT_KID) is not None
    with pytest.raises(UnknownSigningKey):
        cache.get_key("sneaky")


def test_encryption_keys_are_ignored(transport: FakeTransport, keypair: KeyPair):
    enc = dict(keypair.jwk(), kid="enc-key", use="enc")
    transport.jwks_response = (200, {"keys": [enc, keypair.jwk()]})
    cache = make_cache(transport, FakeClock(), min_refresh_interval=0)

    assert cache.key_ids() == [] or "enc-key" not in cache.key_ids()
    with pytest.raises(UnknownSigningKey):
        cache.get_key("enc-key")


def test_missing_kid_resolves_when_exactly_one_key(transport: FakeTransport):
    cache = make_cache(transport, FakeClock())
    assert cache.get_key(None) is not None


def test_missing_kid_is_ambiguous_with_multiple_keys(
    transport: FakeTransport, keypair: KeyPair, rotated_keypair: KeyPair
):
    transport.jwks_response = (200, {"keys": [keypair.jwk(), rotated_keypair.jwk()]})
    cache = make_cache(transport, FakeClock(), min_refresh_interval=0)

    with pytest.raises(UnknownSigningKey):
        cache.get_key(None)
