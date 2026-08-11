"""Shared pytest fixtures for the passport test-suite."""
import pytest

from passport.ratelimit import get_redis


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
