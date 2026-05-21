"""Tests for paperguard.webui.scan_cache — InMemory + Redis backends."""
from __future__ import annotations

import time

import pytest

fakeredis = pytest.importorskip("fakeredis")

from paperguard.webui.scan_cache import (  # noqa: E402
    CacheEntry,
    InMemoryCache,
    RedisCache,
    ScanResultCache,
    _autodetect_backend,
    reset_scan_cache_for_tests,
)


def _entry(severity: str = "NOTE", n: int = 2) -> CacheEntry:
    return CacheEntry(
        payload={
            "paper_identifier": "test",
            "findings": [{"severity": severity}] * n,
        },
        severity_max=severity,
        n_findings=n,
    )


# ---------------------------------------------------------------------------
# InMemoryCache
# ---------------------------------------------------------------------------


def test_inmemory_miss_then_set_then_hit() -> None:
    c = InMemoryCache()
    assert c.get("sha1") is None
    c.set("sha1", _entry(), ttl_seconds=10)
    got = c.get("sha1")
    assert got is not None
    assert got.severity_max == "NOTE"
    assert got.n_findings == 2


def test_inmemory_keys_independent() -> None:
    c = InMemoryCache()
    c.set("sha-A", _entry("CRITICAL", 5), ttl_seconds=10)
    c.set("sha-B", _entry("NOTE", 1), ttl_seconds=10)
    a = c.get("sha-A")
    b = c.get("sha-B")
    assert a is not None and a.severity_max == "CRITICAL"
    assert b is not None and b.severity_max == "NOTE"


def test_inmemory_ttl_expiry() -> None:
    c = InMemoryCache()
    c.set("sha1", _entry(), ttl_seconds=0)  # immediate expiry
    # Small wait to cross monotonic boundary
    time.sleep(0.05)
    assert c.get("sha1") is None


def test_inmemory_ttl_long_window_still_hot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = InMemoryCache()
    # Use a real TTL
    c.set("sha1", _entry(), ttl_seconds=300)
    assert c.get("sha1") is not None


# ---------------------------------------------------------------------------
# RedisCache (via fakeredis)
# ---------------------------------------------------------------------------


def _redis_cache() -> RedisCache:
    return RedisCache(fakeredis.FakeRedis(decode_responses=False))


def test_redis_miss_then_set_then_hit() -> None:
    c = _redis_cache()
    assert c.get("sha1") is None
    c.set("sha1", _entry("SUSPICIOUS", 3), ttl_seconds=60)
    got = c.get("sha1")
    assert got is not None
    assert got.severity_max == "SUSPICIOUS"
    assert got.n_findings == 3


def test_redis_keys_independent() -> None:
    c = _redis_cache()
    c.set("A", _entry("NOTE", 1), ttl_seconds=60)
    c.set("B", _entry("CRITICAL", 5), ttl_seconds=60)
    assert c.get("A").severity_max == "NOTE"  # type: ignore[union-attr]
    assert c.get("B").severity_max == "CRITICAL"  # type: ignore[union-attr]


def test_redis_fail_open_on_get_error() -> None:
    """Backend exception during get → return None (no false hit)."""
    class BrokenClient:
        def get(self, key: str) -> object:
            raise RuntimeError("redis down")

    c = RedisCache(BrokenClient())
    assert c.get("sha1") is None  # fail-open == cache miss


def test_redis_set_failure_silent() -> None:
    """Backend exception during set → log warning, don't raise."""
    class BrokenClient:
        def set(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("redis down")

    c = RedisCache(BrokenClient())
    # Should NOT raise
    c.set("sha1", _entry(), ttl_seconds=10)


def test_redis_malformed_entry_returns_none() -> None:
    """If Redis has garbage at the key, treat as miss + log."""
    client = fakeredis.FakeRedis(decode_responses=False)
    c = RedisCache(client)
    # Write garbage directly bypassing the .set() wrapping
    client.set(c._full_key("sha1"), b"not json {{")
    assert c.get("sha1") is None


def test_redis_missing_field_returns_none() -> None:
    """If Redis has valid JSON but missing fields, treat as miss."""
    import json as _json
    client = fakeredis.FakeRedis(decode_responses=False)
    c = RedisCache(client)
    client.set(c._full_key("sha1"), _json.dumps({"payload": {}}).encode("utf-8"))
    assert c.get("sha1") is None


# ---------------------------------------------------------------------------
# ScanResultCache facade + autodetect
# ---------------------------------------------------------------------------


def test_facade_with_explicit_backend() -> None:
    backend = InMemoryCache()
    cache = ScanResultCache(backend=backend)
    assert cache.backend_name == "InMemoryCache"
    cache.set("sha1", _entry())
    assert cache.get("sha1") is not None


def test_facade_default_ttl() -> None:
    """Default 5-min TTL should make entries stick around."""
    cache = ScanResultCache(backend=InMemoryCache())
    cache.set("sha1", _entry())
    assert cache.get("sha1") is not None


def test_autodetect_no_env_uses_inmemory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAPERGUARD_REDIS_URL", raising=False)
    backend = _autodetect_backend()
    assert type(backend).__name__ == "InMemoryCache"


def test_autodetect_redis_init_failure_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PAPERGUARD_REDIS_URL",
        "redis://nonexistent-host.invalid:6379/0",
    )
    import paperguard.webui.scan_cache as sc

    def boom(cls: type, url: str) -> sc.RedisCache:
        raise RuntimeError("connect refused")

    monkeypatch.setattr(
        sc.RedisCache, "from_url", classmethod(boom)
    )
    backend = sc._autodetect_backend()
    assert type(backend).__name__ == "InMemoryCache"


def test_reset_for_tests() -> None:
    reset_scan_cache_for_tests(InMemoryCache())
    from paperguard.webui.scan_cache import get_scan_cache

    cache = get_scan_cache()
    assert cache.backend_name == "InMemoryCache"


def test_entry_shape() -> None:
    e = CacheEntry(
        payload={"x": 1}, severity_max="CRITICAL", n_findings=10
    )
    assert e.severity_max == "CRITICAL"
    assert e.n_findings == 10
    assert e.payload == {"x": 1}
