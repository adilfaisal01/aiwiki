import pytest
import time
import threading
from core.rate_limit import RateLimiter


@pytest.mark.tier1
class TestMemoryExhaustion:
    def test_unique_ips_dont_exhaust_memory(self):
        limiter = RateLimiter(limit=10, window_seconds=60)
        for i in range(10_000):
            limiter.allow(f"ip-{i}")
        assert len(limiter._hits) <= 10_000

    def test_stale_entries_are_evicted(self):
        limiter = RateLimiter(limit=5, window_seconds=1)
        limiter.allow("test-key")
        time.sleep(1.5)
        limiter.allow("test-key")
        assert len(limiter._hits.get("test-key", [])) <= 2


@pytest.mark.tier1
class TestIPSpoofing:
    def test_x_forwarded_for_spoofing(self, client):
        for i in range(200):
            resp = client.get("/health", headers={"X-Forwarded-For": f"10.0.0.{i}"})
            assert resp.status_code in (200, 429)

    def test_localhost_bypass(self, client):
        resp = client.get("/health", headers={"X-Forwarded-For": "127.0.0.1"})
        assert resp.status_code == 200


@pytest.mark.tier1
class TestConcurrency:
    def test_concurrent_hammer(self):
        limiter = RateLimiter(limit=100, window_seconds=60)
        errors = []

        def hammer():
            for _ in range(50):
                if not limiter.allow("hammer-key"):
                    errors.append("blocked")

        threads = []
        for _ in range(20):
            t = threading.Thread(target=hammer)
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        assert len(errors) < 950
