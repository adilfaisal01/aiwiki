"""Rate limiting for API and registration endpoints.

Provides both an in-memory sliding-window implementation (``RateLimiter``)
and a Redis-backed variant (``RedisRateLimiter``).  The module-level
``api_rate_limiter`` and ``registration_rate_limiter`` singletons are
auto-configured from ``config.REDIS_URL``.
"""

import logging
import time
from collections import defaultdict
from threading import Lock

from core import config

logger = logging.getLogger("aiwiki.rate_limit")

_MAX_ENTRIES = 10_000


class RateLimiter:
    """In-memory sliding-window rate limiter.

    Tracks request timestamps per key within a configurable time window.
    Thread-safe via a ``Lock``.
    """

    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()
        self._last_eviction = time.time()

    def _evict_stale(self):
        """Remove keys that have not been touched in 2x the window."""
        now = time.time()
        if now - self._last_eviction < 120:
            return
        self._last_eviction = now
        cutoff = now - self.window_seconds * 2
        stale_keys = [k for k, v in self._hits.items() if not v or max(v) < cutoff]
        for k in stale_keys:
            del self._hits[k]

    def _enforce_max_entries(self):
        """Evict oldest keys when the total entry count exceeds _MAX_ENTRIES."""
        if len(self._hits) > _MAX_ENTRIES:
            sorted_keys = sorted(self._hits.keys(), key=lambda k: max(self._hits[k]) if self._hits[k] else 0)
            for k in sorted_keys[: len(self._hits) - _MAX_ENTRIES]:
                del self._hits[k]

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._evict_stale()
            window_start = now - self.window_seconds
            hits = [t for t in self._hits[key] if t > window_start]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            self._enforce_max_entries()
            return True

    def retry_after(self, key: str) -> int:
        now = time.time()
        with self._lock:
            hits = self._hits.get(key, [])
            if not hits:
                return 0
            oldest = min(hits)
            return max(1, int(self.window_seconds - (now - oldest)))


class RedisRateLimiter:
    """Redis-backed fixed-window rate limiter.

    Uses ``INCR`` + ``EXPIRE`` on per-window keys for atomic counting.
    """

    def __init__(self, redis_url: str, limit: int, window_seconds: int = 60):
        import redis

        self._redis = redis.from_url(redis_url, decode_responses=True)
        self.limit = limit
        self.window_seconds = window_seconds
        self._redis.ping()

    def allow(self, key: str) -> bool:
        """Check whether a request for *key* is allowed under the rate limit.

        Args:
            key: The identifier to rate-limit.

        Returns:
            True if within the limit, False if rate-limited.
        """
        bucket = f"aiwiki:rl:{key}:{int(time.time() // self.window_seconds)}"
        count = self._redis.incr(bucket)
        if count == 1:
            self._redis.expire(bucket, self.window_seconds + 1)
        return count <= self.limit

    def retry_after(self, key: str) -> int:
        """Return the number of seconds to wait before retrying.

        Args:
            key: The rate-limited identifier.

        Returns:
            Seconds until the rate limit resets (at least 1).
        """
        bucket = f"aiwiki:rl:{key}:{int(time.time() // self.window_seconds)}"
        count = self._redis.incr(bucket)
        if count == 1:
            self._redis.expire(bucket, self.window_seconds + 1)
        return count <= self.limit

    def retry_after(self, key: str) -> int:
        """Return the number of seconds to wait before retrying.

        Args:
            key: The rate-limited identifier.

        Returns:
            Seconds until the rate limit resets (at least 1).
        """
        bucket = f"aiwiki:rl:{key}:{int(time.time() // self.window_seconds)}"
        ttl = self._redis.ttl(bucket)
        return max(1, ttl if ttl and ttl > 0 else self.window_seconds)


def _build_limiter(limit: int) -> RateLimiter | RedisRateLimiter:
    """Construct a rate limiter, preferring Redis when available.

    Falls back to the in-memory ``RateLimiter`` if Redis is not configured
    or unreachable.

    Args:
        limit: Maximum requests per window.

    Returns:
        A configured ``RateLimiter`` or ``RedisRateLimiter`` instance.
    """
    if config.REDIS_URL:
        try:
            limiter = RedisRateLimiter(config.REDIS_URL, limit)
            logger.info("Rate limiter using Redis")
            return limiter
        except Exception as exc:
            logger.warning("Redis rate limiter unavailable, using in-memory fallback: %s", exc)
    return RateLimiter(limit)


def rate_limit_backend() -> str:
    """Report which rate-limit backend is active.

    Returns:
        ``'redis'`` if Redis is available, otherwise ``'memory'``.
    """
    if config.REDIS_URL:
        try:
            import redis

            client = redis.from_url(config.REDIS_URL, decode_responses=True)
            client.ping()
            return "redis"
        except Exception:
            return "memory"
    return "memory"


api_rate_limiter = _build_limiter(config.EXTERNAL_RATE_LIMIT)
registration_rate_limiter = _build_limiter(config.REGISTRATION_RATE_LIMIT)
