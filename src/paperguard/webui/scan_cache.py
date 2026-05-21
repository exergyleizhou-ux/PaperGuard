"""SHA-keyed scan-result cache for the multi-tenant Web UI.

Why this exists
---------------
Two users uploading the *same* PDF (same SHA-256) currently trigger two
full scans — same detectors, same input, identical output, twice the
CPU. For high-traffic multi-tenant deployments this is wasteful.

The cache stores the audit payload keyed by ``sha256(file_bytes)`` with
a short TTL (default 5 min). On cache hit the second upload returns
the cached payload directly; on miss we run the full scan and store
the result.

Two backends behind a single facade, same shape as ``ratelimit.py``:

- **InMemoryCache** — process-local dict with TTL eviction on read.
  Suitable for dev / single-process. Not safe across workers.
- **RedisCache** — Redis ``SET`` with ``EX`` TTL. Safe across
  processes / workers / hosts.

Selection is automatic via ``PAPERGUARD_REDIS_URL`` (shared with the
rate-limiter — same Redis instance, different key prefix).

Failure semantics
-----------------
- Read miss: returns ``None``; the caller runs the scan and may cache.
- Write failure: log a warning, never raise; the scan was successful,
  caching is best-effort.
- Read backend exception: fail-open (return ``None`` → re-scan); never
  serve stale wrong data because Redis is flaky.

Privacy note
------------
Payloads are stored verbatim. **Do not** store cache contents past the
TTL window; rely on Redis TTL for that. The user must trust the
cache-host environment.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    payload: dict[str, Any]
    severity_max: str
    n_findings: int


class CacheBackend(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...
    def set(self, key: str, entry: CacheEntry, ttl_seconds: int) -> None: ...


# ---------------------------------------------------------------------------
# InMemoryCache
# ---------------------------------------------------------------------------


class InMemoryCache:
    """Per-process dict with read-time TTL eviction. NOT safe across workers."""

    def __init__(self) -> None:
        # key -> (expires_at_monotonic, entry)
        self._store: dict[str, tuple[float, CacheEntry]] = {}

    def get(self, key: str) -> CacheEntry | None:
        now = time.monotonic()
        record = self._store.get(key)
        if record is None:
            return None
        expires_at, entry = record
        if now >= expires_at:
            # TTL elapsed; evict + miss
            self._store.pop(key, None)
            return None
        return entry

    def set(self, key: str, entry: CacheEntry, ttl_seconds: int) -> None:
        self._store[key] = (time.monotonic() + ttl_seconds, entry)


# ---------------------------------------------------------------------------
# RedisCache
# ---------------------------------------------------------------------------


class RedisCache:
    """Redis-backed cache using SET/GET + EX TTL.

    Accepts either a real ``redis.Redis`` client or a
    ``fakeredis.FakeRedis`` instance for tests.
    """

    KEY_PREFIX = "paperguard:scan_cache:"

    def __init__(self, client: object) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> RedisCache:
        import redis

        client = redis.Redis.from_url(url, decode_responses=False)
        return cls(client)

    def _full_key(self, key: str) -> str:
        return f"{self.KEY_PREFIX}{key}"

    def get(self, key: str) -> CacheEntry | None:
        try:
            raw = self._client.get(self._full_key(key))  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "RedisCache.get failed for key=%s: %s — fail-open (re-scan)",
                key, e,
            )
            return None
        if raw is None:
            return None
        try:
            data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            return CacheEntry(
                payload=data["payload"],
                severity_max=data["severity_max"],
                n_findings=int(data["n_findings"]),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(
                "RedisCache.get malformed entry for key=%s: %s — re-scan",
                key, e,
            )
            return None

    def set(self, key: str, entry: CacheEntry, ttl_seconds: int) -> None:
        body = {
            "payload": entry.payload,
            "severity_max": entry.severity_max,
            "n_findings": entry.n_findings,
        }
        try:
            self._client.set(  # type: ignore[attr-defined]
                self._full_key(key),
                json.dumps(body, ensure_ascii=False),
                ex=ttl_seconds,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "RedisCache.set failed for key=%s: %s — caching skipped",
                key, e,
            )


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------


class ScanResultCache:
    """Public scan-cache wrapping a backend + default TTL.

    Default TTL: 5 minutes. Override per-call via ``set(..., ttl_seconds=)``.
    """

    DEFAULT_TTL_SECONDS = 300

    def __init__(self, backend: CacheBackend | None = None) -> None:
        if backend is not None:
            self._backend: CacheBackend = backend
        else:
            self._backend = _autodetect_backend()

    def get(self, sha256_hex: str) -> CacheEntry | None:
        return self._backend.get(sha256_hex)

    def set(
        self,
        sha256_hex: str,
        entry: CacheEntry,
        ttl_seconds: int | None = None,
    ) -> None:
        self._backend.set(
            sha256_hex,
            entry,
            ttl_seconds or self.DEFAULT_TTL_SECONDS,
        )

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__


def _autodetect_backend() -> CacheBackend:
    """Pick Redis if PAPERGUARD_REDIS_URL is set; otherwise in-memory."""
    url = os.environ.get("PAPERGUARD_REDIS_URL")
    if url:
        try:
            return RedisCache.from_url(url)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "PAPERGUARD_REDIS_URL set to %r but RedisCache init "
                "failed (%s); falling back to InMemoryCache",
                url, e,
            )
    return InMemoryCache()


_GLOBAL_CACHE: ScanResultCache | None = None


def get_scan_cache() -> ScanResultCache:
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is None:
        _GLOBAL_CACHE = ScanResultCache()
    return _GLOBAL_CACHE


def reset_scan_cache_for_tests(backend: CacheBackend | None = None) -> None:
    global _GLOBAL_CACHE
    _GLOBAL_CACHE = ScanResultCache(backend=backend)
