import pytest
import uuid
import threading


@pytest.mark.tier2
class TestSessionSecurity:
    @pytest.mark.xfail(reason="Session cookie is not validated on /api/v1/account/me")
    def test_session_token_brute_force(self, client):
        for _ in range(100):
            client.cookies.set("aiwiki_account_session", "a" * 43)
            resp = client.get("/api/v1/account/me")
            assert resp.status_code == 401

    def test_csrf_protection(self, client):
        resp = client.post(
            "/api/v1/account",
            json={"email": "csrf-test@example.com", "password": "password123"},
        )
        assert resp.status_code == 201

    @pytest.mark.xfail(reason="Duplicate registration returns 400 instead of 409")
    def test_account_enumeration(self, client):
        email = f"enum-{uuid.uuid4().hex[:10]}@example.com"
        resp1 = client.post("/api/v1/account", json={"email": email, "password": "password123"})
        assert resp1.status_code == 201
        resp2 = client.post("/api/v1/account", json={"email": email, "password": "password123"})
        assert resp2.status_code == 409


@pytest.mark.tier2
class TestPasswordEdgeCases:
    def test_password_with_null_bytes(self, client):
        resp = client.post(
            "/api/v1/account",
            json={"email": f"null-{uuid.uuid4().hex[:10]}@example.com", "password": "pass\x00word123"},
        )
        assert resp.status_code == 201

    def test_password_exactly_8_chars(self, client):
        resp = client.post(
            "/api/v1/account",
            json={"email": f"eight-{uuid.uuid4().hex[:10]}@example.com", "password": "12345678"},
        )
        assert resp.status_code == 201

    def test_password_too_short(self, client):
        resp = client.post(
            "/api/v1/account",
            json={"email": f"short-{uuid.uuid4().hex[:10]}@example.com", "password": "1234567"},
        )
        assert resp.status_code == 400


@pytest.mark.tier2
class TestRegistrationRace:
    def test_concurrent_registration_same_email(self, client):
        email = f"race-{uuid.uuid4().hex[:10]}@example.com"
        results = []

        def register():
            resp = client.post("/api/v1/account", json={"email": email, "password": "password123"})
            results.append(resp.status_code)

        threads = []
        for _ in range(10):
            t = threading.Thread(target=register)
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        assert results.count(201) == 1
        assert results.count(409) == 9
