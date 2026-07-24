import pytest


@pytest.mark.tier1
class TestChunkedEncoding:
    def test_chunked_encoding_bypass(self, client):
        resp = client.post(
            "/api/v1/account",
            content=b"a" * 100_000_000,
            headers={
                "Transfer-Encoding": "chunked",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 413

    @pytest.mark.xfail(reason="Negative content-length causes int() ValueError")
    def test_negative_content_length(self, client):
        resp = client.post(
            "/api/v1/account",
            json={"email": "test@example.com", "password": "password123"},
            headers={"content-length": "-1"},
        )
        assert resp.status_code in (200, 400, 413)

    @pytest.mark.xfail(reason="Missing content-length with JSON body is not rejected")
    def test_missing_content_length(self, client):
        resp = client.post(
            "/api/v1/account",
            json={"email": "test@example.com", "password": "password123"},
        )
        assert resp.status_code in (200, 400)

    def test_zero_byte_body(self, client):
        resp = client.post("/api/v1/account", content=b"", headers={"content-type": "application/json"})
        assert resp.status_code in (400, 413, 422)

    def test_oversized_body(self, client):
        resp = client.post(
            "/api/v1/account",
            json={"data": "x" * 20_000_000},
        )
        assert resp.status_code == 413
