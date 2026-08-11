"""Tests for the Redis-backed rate limiter, account lockout and proxy middleware."""
import pytest
from django.test import RequestFactory
from django.test.utils import override_settings

from passport.middleware import TrustedProxyMiddleware
from passport.ratelimit import (
    AccountLockout,
    OAuthStateStore,
    RateLimiter,
    check_rate_limit,
)


class _FakeRequest:
    def __init__(self, remote, path="/x", xff=None, user=None):
        self.META = {"REMOTE_ADDR": remote, "PATH_INFO": path}
        if xff is not None:
            self.META["HTTP_X_FORWARDED_FOR"] = xff
        self.path = path
        self.user = user


def test_account_lockout_locks_after_threshold():
    lock = AccountLockout()
    idk = "lock-test@example.com"
    lock.clear(idk)
    for _ in range(4):
        count, _ = lock.register_failure(idk, threshold=5, window=900)
    assert lock.is_locked(idk, threshold=5) is False
    count, ttl = lock.register_failure(idk, threshold=5, window=900)
    assert count == 5
    assert lock.is_locked(idk, threshold=5) is True
    assert ttl > 0
    lock.clear(idk)
    assert lock.is_locked(idk, threshold=5) is False


def test_account_lockout_is_per_identifier_not_ip():
    lock = AccountLockout()
    a, b = "nat-a@example.com", "nat-b@example.com"
    lock.clear(a)
    lock.clear(b)
    for _ in range(5):
        lock.register_failure(a, threshold=5, window=900)
    assert lock.is_locked(a, threshold=5) is True
    assert lock.is_locked(b, threshold=5) is False  # independent identifiers


def test_check_rate_limit_keys_on_identifier_not_ip():
    rl = RateLimiter()
    for idk in ("acct1", "acct2"):
        rl.client.delete(f"ratelimit:pwd-login:{idk}:/api/v1/login/")
    req = _FakeRequest(remote="203.0.113.7", path="/api/v1/login/")
    # Two accounts behind the SAME NAT IP are limited independently.
    assert check_rate_limit(req, limit=2, window=60, scope="pwd-login", identifier="acct1") is True
    assert check_rate_limit(req, limit=2, window=60, scope="pwd-login", identifier="acct1") is True
    assert check_rate_limit(req, limit=2, window=60, scope="pwd-login", identifier="acct1") is False
    assert check_rate_limit(req, limit=2, window=60, scope="pwd-login", identifier="acct2") is True


@override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
def test_trusted_proxy_honours_xff_only_when_peer_trusted():
    rf = RequestFactory()
    req = rf.post(
        "/", HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1", REMOTE_ADDR="10.0.0.1"
    )
    TrustedProxyMiddleware(get_response=lambda r: r).process_request(req)
    assert req.META["REMOTE_ADDR"] == "203.0.113.9"
    assert "HTTP_X_FORWARDED_FOR" in req.META


@override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
def test_untrusted_peer_xff_is_stripped():
    rf = RequestFactory()
    req = rf.post("/", HTTP_X_FORWARDED_FOR="203.0.113.9", REMOTE_ADDR="198.51.100.7")
    TrustedProxyMiddleware(get_response=lambda r: r).process_request(req)
    assert req.META["REMOTE_ADDR"] == "198.51.100.7"
    assert "HTTP_X_FORWARDED_FOR" not in req.META


def test_rate_limiter_allows_up_to_limit_then_blocks():
    rl = RateLimiter()
    key = "test:ratelimit:demo"
    rl.client.delete(key)
    for _ in range(5):
        assert rl.is_allowed(key, limit=5, window=60) is True
    assert rl.is_allowed(key, limit=5, window=60) is False


def test_rate_limiter_resets_after_window():
    rl = RateLimiter()
    key = "test:ratelimit:window"
    rl.client.delete(key)
    assert rl.is_allowed(key, limit=1, window=60) is True
    assert rl.is_allowed(key, limit=1, window=60) is False
    rl.client.delete(key)  # simulate window expiry
    assert rl.is_allowed(key, limit=1, window=60) is True


def test_state_store_save_consume_is_one_shot():
    store = OAuthStateStore()
    state = store.save("github", "https://app/cb")
    stored = store.consume(state)
    assert stored["provider"] == "github"
    assert stored["redirect_uri"] == "https://app/cb"
    # bind-mode metadata is part of the payload (§9.2); defaults when not binding.
    assert stored["link_mode"] is False
    assert stored["passport_id"] is None
    assert store.consume(state) is None  # already consumed


def test_state_store_rejects_unknown_state():
    store = OAuthStateStore()
    assert store.consume("nope") is None
