import time
from collections import defaultdict
from threading import Lock

import config


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            window_start = now - self.window_seconds
            hits = [t for t in self._hits[key] if t > window_start]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True

    def retry_after(self, key: str) -> int:
        now = time.time()
        with self._lock:
            hits = self._hits.get(key, [])
            if not hits:
                return 0
            oldest = min(hits)
            return max(1, int(self.window_seconds - (now - oldest)))


api_rate_limiter = RateLimiter(config.EXTERNAL_RATE_LIMIT)
registration_rate_limiter = RateLimiter(config.REGISTRATION_RATE_LIMIT)
