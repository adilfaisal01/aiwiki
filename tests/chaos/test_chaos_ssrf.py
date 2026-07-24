import pytest
from core.webhooks import validate_webhook_url, dispatch
from urllib.parse import urlparse


@pytest.mark.tier1
class TestWebhookURLParsing:
    def test_url_with_credentials(self):
        valid, msg = validate_webhook_url("http://user:pass@evil.com/hook")
        assert valid is True

    def test_url_with_fragment(self):
        valid, msg = validate_webhook_url("http://evil.com/hook#fragment")
        assert valid is True

    def test_url_with_at_sign_in_path(self):
        valid, msg = validate_webhook_url("http://evil.com@127.0.0.1:8080/hook")
        assert valid is False

    @pytest.mark.xfail(reason="IPv6 private ranges (fc00::/7, fe80::/10) not blocked")
    def test_ipv6_private_range(self):
        valid, msg = validate_webhook_url("http://[fc00::1]:8080/hook")
        assert valid is False

    @pytest.mark.xfail(reason="IPv6 link-local addresses (fe80::/10) not blocked")
    def test_ipv6_link_local(self):
        valid, msg = validate_webhook_url("http://[fe80::1]:8080/hook")
        assert valid is False

    def test_dns_rebinding_simulation(self):
        valid, msg = validate_webhook_url("http://127.0.0.1:8080/hook")
        assert valid is False

    def test_cloud_metadata(self):
        valid, msg = validate_webhook_url("http://169.254.169.254/latest/meta-data/")
        assert valid is False

    def test_self_referencing_webhook(self):
        valid, msg = validate_webhook_url("http://localhost:8000/webhook")
        assert valid is False


@pytest.mark.tier1
class TestWebhookDispatch:
    def test_dispatch_to_slow_target(self, monkeypatch):
        import httpx
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: (_ for _ in ()).throw(httpx.TimeoutException("timeout")))
        dispatch(agent_id=1, event="test", payload={"key": "value"})

    def test_dispatch_to_invalid_url(self, monkeypatch):
        monkeypatch.setattr("core.database.get_agent_webhook_url", lambda aid: "not-a-url")
        dispatch(agent_id=1, event="test", payload={})
