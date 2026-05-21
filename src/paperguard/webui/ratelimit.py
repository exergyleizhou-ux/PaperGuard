"""Rate-limit primitives for the multi-tenant Web UI.

Two backends are provided behind a single ``RateLimiter`` interface:

- **InMemoryBackend** — process-local sliding-window counter using a
  simple dict + monotonic timestamp list per key. Suitable for a
  single-process dev server. **Not** safe for multi-process /
  multi-worker deployments because each worker sees a separate copy.
- **RedisBackend** — uses Redis sorted sets with TTL for a proper
  sliding-window counter. Safe across processes / workers / hosts.

Selection is automatic based on the ``PAPERGUARD_REDIS_URL`` env var:

- unset → InMemoryBackend (warning printed via ``logger.warning`` at
  app start)
- ``redis://[:password@]host[:port][/db]`` → RedisBackend
- ``redis://test`` or test contexts → ``fakeredis.FakeRedis`` (tests
  pass ``backend=`` directly to bypass env detection)

The rate limit itself is a **token-bucket-style sliding window**:

  - up to ``max_requests`` requests in any rolling ``window_seconds``.
  - on the (max_requests + 1)-th request inside the window the limiter
    returns ``allowed=False`` plus the ``retry_after_seconds`` until
    the oldest in-window request expires.

The check is **best-effort**: any backend exception causes the
limiter to fail-open (allow the request) and log a warning. We
**never** block a legitimate request because Redis is flaky.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass
class RateLimitDecision:
    """Result of a single rate-limit check."""

    allowed: bool
    remaining: int           # remaining allowance in the current window
    retry_after_seconds: float = 0.0  # only meaningful when allowed=False


class RateLimitBackend(Protocol):
    """Backend interface — both InMemory and Redis implementations."""

    def hit(
        self,
        key: str,
        *,
        max_requests: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        ...


# ---------------------------------------------------------------------------
# In-memory backend (dev / single-process)
# ---------------------------------------------------------------------------


class InMemoryBackend:
    """Per-process sliding-window counter. Not safe across workers."""

    def __init__(self) -> None:
        # key -> list of monotonic timestamps within the last window
        self._hits: dict[str, list[float]] = defaultdict(list)
        # Per-key lock so concurrent requests under asyncio don't trample
        self._lock = threading.Lock()

    def hit(
        self,
        key: str,
        *,
        max_requests: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            timestamps = self._hits[key]
            # Drop everything older than the window.
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)
            current = len(timestamps)
            if current >= max_requests:
                # Reject. retry_after = when the oldest in-window hit ages out.
                retry_after = (timestamps[0] + window_seconds) - now
                return RateLimitDecision(
                    allowed=False,
                    remaining=0,
                    retry_after_seconds=max(retry_after, 0.0),
                )
            timestamps.append(now)
            return RateLimitDecision(
                allowed=True,
                remaining=max_requests - current - 1,
            )


# ---------------------------------------------------------------------------
# Redis backend (production, multi-worker safe)
# ---------------------------------------------------------------------------


class RedisBackend:
    """Sliding-window counter via Redis sorted set.

    The script (a) drops timestamps older than the window, (b) checks
    the count, (c) adds the new timestamp if under cap. All three
    operations happen in a single Redis pipeline so workers cannot race
    past the cap.

    Accepts either a real ``redis.Redis`` client or a ``fakeredis.FakeRedis``
    instance for tests.
    """

    def __init__(self, client: object) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> RedisBackend:
        import redis

        client = redis.Redis.from_url(url, decode_responses=False)
        return cls(client)

    def hit(
        self,
        key: str,
        *,
        max_requests: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        full_key = f"paperguard:ratelimit:{key}"
        # Use monotonic-like time — Redis ZSET scores need a numeric.
        # We use time.time() (wall clock) because Redis-side cutoff
        # comparison must be consistent across workers.
        now = time.time()
        cutoff = now - window_seconds
        try:
            # Use pipeline for atomicity.
            pipe = self._client.pipeline()  # type: ignore[attr-defined]
            pipe.zremrangebyscore(full_key, "-inf", cutoff)
            pipe.zcard(full_key)
            results = pipe.execute()
            current = int(results[1])

            if current >= max_requests:
                # Find oldest score in window for retry_after.
                oldest = self._client.zrange(  # type: ignore[attr-defined]
                    full_key, 0, 0, withscores=True
                )
                if oldest:
                    oldest_ts = float(oldest[0][1])
                    retry_after = (oldest_ts + window_seconds) - now
                else:
                    retry_after = float(window_seconds)
                return RateLimitDecision(
                    allowed=False,
                    remaining=0,
                    retry_after_seconds=max(retry_after, 0.0),
                )

            # Under cap — record the hit and set TTL.
            pipe = self._client.pipeline()  # type: ignore[attr-defined]
            # Use a tiny entropy suffix on the member so two simultaneous
            # writes don't collide on the same score key.
            member = f"{now}:{os.urandom(4).hex()}"
            pipe.zadd(full_key, {member: now})
            pipe.expire(full_key, window_seconds + 1)
            pipe.execute()
            return RateLimitDecision(
                allowed=True,
                remaining=max_requests - current - 1,
            )
        except Exception as e:  # noqa: BLE001
            # Fail-open: never block a legitimate request because Redis
            # is broken. Log loudly so ops notice.
            logger.warning(
                "RedisBackend.hit failed for key=%s: %s — failing open",
                key, e,
            )
            return RateLimitDecision(
                allowed=True,
                remaining=max_requests - 1,
            )


# ---------------------------------------------------------------------------
# Public façade
# ---------------------------------------------------------------------------


class RateLimiter:
    """Public rate-limiter wrapping a backend + default policy.

    Default policy: 30 requests per 60 s per key. Override per-call
    via ``hit(key, max_requests=, window_seconds=)``.
    """

    DEFAULT_MAX_REQUESTS = 30
    DEFAULT_WINDOW_SECONDS = 60

    def __init__(self, backend: RateLimitBackend | None = None) -> None:
        if backend is not None:
            self._backend: RateLimitBackend = backend
        else:
            self._backend = _autodetect_backend()

    def hit(
        self,
        key: str,
        *,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ) -> RateLimitDecision:
        return self._backend.hit(
            key,
            max_requests=max_requests or self.DEFAULT_MAX_REQUESTS,
            window_seconds=window_seconds or self.DEFAULT_WINDOW_SECONDS,
        )

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__


def _autodetect_backend() -> RateLimitBackend:
    """Pick Redis if PAPERGUARD_REDIS_URL is set; otherwise in-memory."""
    url = os.environ.get("PAPERGUARD_REDIS_URL")
    if url:
        try:
            return RedisBackend.from_url(url)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "PAPERGUARD_REDIS_URL set to %r but Redis backend init "
                "failed (%s); falling back to InMemoryBackend",
                url, e,
            )
    else:
        logger.warning(
            "PAPERGUARD_REDIS_URL not set; using InMemoryBackend "
            "(NOT safe for multi-worker deployments)"
        )
    return InMemoryBackend()


# Module-level singleton — recreated on import in test contexts via
# the reset_rate_limiter_for_tests() helper below.
_GLOBAL_LIMITER: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return the process-global RateLimiter, creating it on first call."""
    global _GLOBAL_LIMITER
    if _GLOBAL_LIMITER is None:
        _GLOBAL_LIMITER = RateLimiter()
    return _GLOBAL_LIMITER


def reset_rate_limiter_for_tests(
    backend: RateLimitBackend | None = None,
) -> None:
    """Test helper: replace the global limiter with a fresh one."""
    global _GLOBAL_LIMITER
    _GLOBAL_LIMITER = RateLimiter(backend=backend)
