"""Tests for paperguard.webui.ratelimit — InMemory + Redis backends.

Covers:
- InMemoryBackend allows up to max_requests in window, rejects (max+1)-th
- InMemoryBackend resets after window expires
- RedisBackend (via fakeredis) — same semantics
- RedisBackend fails open on backend exceptions
- RateLimiter facade picks Redis when env var set, InMemory otherwise
- Decision.retry_after_seconds is sensible
"""
from __future__ import annotations

import time

import pytest

fakeredis = pytest.importorskip("fakeredis")

from paperguard.webui.ratelimit import (  # noqa: E402
    InMemoryBackend,
    RateLimitDecision,
    RateLimiter,
    RedisBackend,
    _autodetect_backend,
    reset_rate_limiter_for_tests,
)

# ---------------------------------------------------------------------------
# InMemoryBackend
# ---------------------------------------------------------------------------


def test_inmemory_allows_under_cap() -> None:
    b = InMemoryBackend()
    for i in range(5):
        d = b.hit("user-1", max_requests=5, window_seconds=10)
        assert d.allowed, f"hit {i+1}/5 should be allowed"
        assert d.remaining == 4 - i


def test_inmemory_rejects_at_cap() -> None:
    b = InMemoryBackend()
    for _ in range(3):
        b.hit("user-1", max_requests=3, window_seconds=10)
    d = b.hit("user-1", max_requests=3, window_seconds=10)
    assert d.allowed is False
    assert d.remaining == 0
    assert d.retry_after_seconds > 0


def test_inmemory_keys_independent() -> None:
    """Different keys should NOT share the same bucket."""
    b = InMemoryBackend()
    for _ in range(5):
        b.hit("user-A", max_requests=5, window_seconds=10)
    # user-A is now capped, user-B should still be empty.
    d = b.hit("user-B", max_requests=5, window_seconds=10)
    assert d.allowed
    assert d.remaining == 4


def test_inmemory_window_eviction(monkeypatch: pytest.MonkeyPatch) -> None:
    """After window expires, old hits should be evicted."""
    b = InMemoryBackend()
    base = [1000.0]

    def fake_mono() -> float:
        return base[0]

    monkeypatch.setattr("paperguard.webui.ratelimit.time.monotonic", fake_mono)
    # 5 hits at t=1000
    for _ in range(5):
        b.hit("user-1", max_requests=5, window_seconds=10)
    # At t=1011 the window has passed → next hit should be allowed
    base[0] = 1011.0
    d = b.hit("user-1", max_requests=5, window_seconds=10)
    assert d.allowed


# ---------------------------------------------------------------------------
# RedisBackend (via fakeredis)
# ---------------------------------------------------------------------------


def _redis_backend() -> RedisBackend:
    client = fakeredis.FakeRedis(decode_responses=False)
    return RedisBackend(client)


def test_redis_allows_under_cap() -> None:
    b = _redis_backend()
    for i in range(5):
        d = b.hit("user-1", max_requests=5, window_seconds=10)
        assert d.allowed
        assert d.remaining == 4 - i


def test_redis_rejects_at_cap() -> None:
    b = _redis_backend()
    for _ in range(3):
        b.hit("user-1", max_requests=3, window_seconds=10)
    d = b.hit("user-1", max_requests=3, window_seconds=10)
    assert d.allowed is False
    assert d.remaining == 0
    assert d.retry_after_seconds >= 0


def test_redis_keys_independent() -> None:
    b = _redis_backend()
    for _ in range(5):
        b.hit("user-A", max_requests=5, window_seconds=10)
    d = b.hit("user-B", max_requests=5, window_seconds=10)
    assert d.allowed


def test_redis_fail_open_on_backend_error() -> None:
    """If Redis raises, fail open (allow the request) and log a warning."""
    class BrokenClient:
        def pipeline(self) -> object:
            raise RuntimeError("redis is down")

    b = RedisBackend(BrokenClient())
    d = b.hit("user-1", max_requests=3, window_seconds=10)
    # Fail-open semantics: allowed=True even though backend exploded.
    assert d.allowed is True
    assert d.remaining >= 0


# ---------------------------------------------------------------------------
# RateLimiter facade + autodetect
# ---------------------------------------------------------------------------


def test_facade_with_explicit_backend() -> None:
    backend = InMemoryBackend()
    limiter = RateLimiter(backend=backend)
    assert limiter.backend_name == "InMemoryBackend"
    d = limiter.hit("k", max_requests=2, window_seconds=10)
    assert d.allowed


def test_facade_uses_default_policy() -> None:
    """If max/window are omitted, fall back to DEFAULT_* class attrs."""
    backend = InMemoryBackend()
    limiter = RateLimiter(backend=backend)
    # Default is 30 / 60s. Fire 30 and expect 30th still allowed.
    last = None
    for _ in range(30):
        last = limiter.hit("user-1")
    assert last is not None
    assert last.allowed
    d31 = limiter.hit("user-1")
    assert d31.allowed is False


def test_autodetect_no_env_uses_inmemory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPERGUARD_REDIS_URL", raising=False)
    backend = _autodetect_backend()
    assert type(backend).__name__ == "InMemoryBackend"


def test_autodetect_bad_redis_url_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If PAPERGUARD_REDIS_URL is set but Redis init fails, fall back to InMemory."""
    monkeypatch.setenv(
        "PAPERGUARD_REDIS_URL",
        "redis://nonexistent-host-12345.invalid:6379/0",
    )
    # autodetect should swallow the exception — redis.from_url is lazy
    # so we patch to force a failure.
    import paperguard.webui.ratelimit as rl

    def boom(url: str) -> rl.RedisBackend:  # type: ignore[no-untyped-def]
        raise RuntimeError("connection refused")

    monkeypatch.setattr(rl.RedisBackend, "from_url", classmethod(lambda cls, url: boom(url)))
    backend = rl._autodetect_backend()
    assert type(backend).__name__ == "InMemoryBackend"


def test_reset_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """reset_rate_limiter_for_tests should replace the global limiter."""
    monkeypatch.delenv("PAPERGUARD_REDIS_URL", raising=False)
    reset_rate_limiter_for_tests(InMemoryBackend())
    from paperguard.webui.ratelimit import get_rate_limiter

    limiter = get_rate_limiter()
    assert limiter.backend_name == "InMemoryBackend"


# ---------------------------------------------------------------------------
# Sanity: RateLimitDecision shape
# ---------------------------------------------------------------------------


def test_decision_shape() -> None:
    d = RateLimitDecision(allowed=True, remaining=5, retry_after_seconds=0.0)
    assert d.allowed is True
    assert d.remaining == 5
    assert d.retry_after_seconds == 0.0
    d2 = RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=3.5)
    assert d2.allowed is False
    assert d2.retry_after_seconds == 3.5


def test_inmemory_unused_window_param() -> None:
    """The window_seconds in InMemoryBackend should be honored in eviction."""
    b = InMemoryBackend()
    d = b.hit("k", max_requests=2, window_seconds=1)
    assert d.allowed
    d = b.hit("k", max_requests=2, window_seconds=1)
    assert d.allowed
    d = b.hit("k", max_requests=2, window_seconds=1)
    assert d.allowed is False
    # Wait for the window to expire
    time.sleep(1.1)
    d = b.hit("k", max_requests=2, window_seconds=1)
    assert d.allowed
