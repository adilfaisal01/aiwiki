import pytest
from core.webhooks import dispatch


@pytest.mark.tier3
class TestThreadExplosion:
    def test_1000_simultaneous_dispatches(self, monkeypatch):
        monkeypatch.setattr("core.database.get_agent_webhook_url", lambda aid: "http://example.com/hook")
        import httpx
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: None)
        for i in range(1000):
            dispatch(agent_id=1, event="test", payload={"i": i})


@pytest.mark.tier3
class TestSlowTarget:
    def test_dispatch_to_never_responds(self, monkeypatch):
        import httpx
        def slow_post(*a, **kw):
            import time
            time.sleep(30)
            return None
        monkeypatch.setattr(httpx, "post", slow_post)
        monkeypatch.setattr("core.database.get_agent_webhook_url", lambda aid: "http://slow.example.com")
        dispatch(agent_id=1, event="test", payload={})


@pytest.mark.tier3
class TestRedirectChain:
    def test_dispatch_with_redirect(self, monkeypatch):
        import httpx
        monkeypatch.setattr("core.database.get_agent_webhook_url", lambda aid: "http://example.com/redirect")
        dispatch(agent_id=1, event="test", payload={})
