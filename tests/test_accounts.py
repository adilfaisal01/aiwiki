import re
import uuid
from io import BytesIO

import pytest

from core import avatar_upload
from core import passwords


UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

TEST_PASSWORD = "password123"


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def register(client, email: str | None = None, password: str = TEST_PASSWORD):
    return client.post(
        "/api/v1/account",
        json={"email": email or unique_email(), "password": password},
    )


@pytest.fixture()
def signed_in_client(client):
    response = register(client)
    assert response.status_code == 201
    return client


def test_password_hash_roundtrip():
    stored = passwords.hash_password("secret-pass")
    assert passwords.verify_password("secret-pass", stored)
    assert not passwords.verify_password("wrong-pass", stored)


def test_get_account_unauthenticated(client):
    response = client.get("/api/v1/account")
    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is False
    assert "avatar_upload_enabled" in payload


def test_register_sets_cookie_and_uuid(client):
    email = unique_email("register")
    response = register(client, email=email)
    assert response.status_code == 201
    data = response.json()
    assert UUID_RE.match(data["id"])
    assert data["email"] == email
    assert data["created_at"]
    assert "aiwiki_account_session" in response.cookies

    me = client.get("/api/v1/account")
    assert me.status_code == 200
    payload = me.json()
    assert payload["authenticated"] is True
    assert payload["id"] == data["id"]
    assert payload["email"] == email


def test_register_rejects_duplicate_email(client):
    email = unique_email("duplicate")
    register(client, email=email)
    client.post("/api/v1/account/logout")
    response = register(client, email=email)
    assert response.status_code == 409


def test_register_requires_password_length(client):
    response = client.post("/api/v1/account", json={"email": "a@b.com", "password": "short"})
    assert response.status_code == 400


def test_register_returns_existing_when_logged_in(signed_in_client):
    me = signed_in_client.get("/api/v1/account").json()
    response = register(
        signed_in_client,
        email=unique_email("ignored"),
    )
    assert response.status_code == 200
    assert response.json()["email"] == me["email"]


def test_logout_clears_session(signed_in_client):
    logout = signed_in_client.post("/api/v1/account/logout")
    assert logout.status_code == 200
    assert logout.json() == {"ok": True}

    me = signed_in_client.get("/api/v1/account")
    assert me.json()["authenticated"] is False


def test_home_includes_account_menu(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="account-menu"' in response.text
    assert "Pricing" in response.text
    assert "account_menu.js" in response.text


def test_account_login_page(client):
    response = client.get("/account/login")
    assert response.status_code == 200
    assert "Account" in response.text
    assert 'id="account-panel-register"' in response.text
    assert 'id="account-panel-login"' in response.text
    assert 'type="email"' in response.text
    assert "account_login.js" in response.text


def test_account_login_redirects_when_signed_in(signed_in_client):
    response = signed_in_client.get("/account/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/account"


def test_account_page_requires_login(client):
    response = client.get("/account", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/account/login"


def test_account_settings_requires_login(client):
    response = client.get("/account/settings", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/account/login"


def test_legacy_session_redirects_to_register(client):
    import core.database as db
    import secrets
    import uuid

    user_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    ts = db.now()
    conn = db.get_db()
    p = db._param_style()
    db._execute(
        conn,
        f"INSERT INTO users (id, session_token, created_at) VALUES ({p}, {p}, {p})",
        (user_id, token, ts),
    )
    conn.commit()
    conn.close()

    client.cookies.set("aiwiki_account_session", token)
    response = client.get("/account", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/account/login?mode=register"


def test_legacy_session_can_complete_registration(client):
    import core.database as db
    import secrets
    import uuid

    user_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    ts = db.now()
    conn = db.get_db()
    p = db._param_style()
    db._execute(
        conn,
        f"INSERT INTO users (id, session_token, created_at) VALUES ({p}, {p}, {p})",
        (user_id, token, ts),
    )
    conn.commit()
    conn.close()

    client.cookies.set("aiwiki_account_session", token)
    email = unique_email("upgrade")
    response = client.post("/api/v1/account", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200
    assert response.json()["email"] == email

    login = client.post("/api/v1/account/logout")
    assert login.status_code == 200
    login = client.post(
        "/api/v1/account/login",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert login.status_code == 200


def test_account_page(signed_in_client):
    me = signed_in_client.get("/api/v1/account").json()
    response = signed_in_client.get("/account")
    assert response.status_code == 200
    assert me["email"] in response.text
    assert "account_settings.js" in response.text
    assert 'href="#account-profile"' in response.text
    assert "mw-page-toolbar" in response.text


def test_account_settings_page(signed_in_client):
    response = signed_in_client.get("/account/settings")
    assert response.status_code == 200
    assert "Preferences" in response.text
    assert "APIs" in response.text
    assert 'href="#account-apis"' in response.text
    assert "account_settings_apis.js" in response.text


def test_account_apis_requires_login(client):
    response = client.get("/api/v1/account/apis")
    assert response.status_code == 401


def test_register_links_agent_to_logged_in_user(signed_in_client):
    import uuid

    name = f"AcctBot{uuid.uuid4().hex[:8]}"
    reg = signed_in_client.post("/api/v1/register", json={"name": name})
    assert reg.status_code == 200
    apis = signed_in_client.get("/api/v1/account/apis")
    assert apis.status_code == 200
    agents = apis.json()["agents"]
    assert any(agent["name"] == name for agent in agents)


def test_link_account_apis(signed_in_client):
    import uuid

    import core.database as db

    name = f"LinkBot{uuid.uuid4().hex[:8]}"
    reg = signed_in_client.post("/api/v1/register", json={"name": name})
    assert reg.status_code == 200
    api_key = reg.json()["api_key"]

    conn = db.get_db()
    p = db._param_style()
    db._execute(conn, f"UPDATE external_agents SET user_id = NULL WHERE name = {p}", (name,))
    conn.commit()
    conn.close()

    link = signed_in_client.post(
        "/api/v1/account/apis/link",
        json={"api_keys": [api_key]},
    )
    assert link.status_code == 200
    payload = link.json()
    assert payload["linked"] == 1
    assert any(agent["name"] == name for agent in payload["agents"])


def test_update_account_locale(signed_in_client):
    response = signed_in_client.patch("/api/v1/account/locale", json={"locale": "de"})
    assert response.status_code == 200
    assert response.json()["locale"] == "de"
    assert signed_in_client.cookies.get("aiwiki_locale") == "de"

    page = signed_in_client.get("/account/settings")
    assert response.status_code == 200
    assert "Sprache" in page.text
    assert "Einstellungen" in page.text


def test_login_with_email_and_password(client):
    email = unique_email("login")
    register(client, email=email)
    client.post("/api/v1/account/logout")

    login = client.post(
        "/api/v1/account/login",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["email"] == email
    assert "aiwiki_account_session" in login.cookies


def test_login_rejects_wrong_password(client):
    email = unique_email("wrongpass")
    register(client, email=email)
    client.post("/api/v1/account/logout")

    response = client.post(
        "/api/v1/account/login",
        json={"email": email, "password": "wrong-password"},
    )
    assert response.status_code == 401


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_login_unknown_email(client):
    response = client.post(
        "/api/v1/account/login",
        json={"email": "missing@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 401


def test_patch_avatar_url(signed_in_client):
    response = signed_in_client.patch(
        "/api/v1/account",
        json={"avatar_url": "https://example.com/avatar.png"},
    )
    assert response.status_code == 200
    assert response.json()["avatar_url"] == "https://example.com/avatar.png"


def test_patch_avatar_url_rejects_invalid_scheme(signed_in_client):
    response = signed_in_client.patch(
        "/api/v1/account",
        json={"avatar_url": "data:image/png;base64,abc"},
    )
    assert response.status_code == 400


def test_avatar_upload_stores_external_link_only(signed_in_client, monkeypatch):
    def fake_upload(content: bytes, filename: str, content_type: str) -> str:
        assert content.startswith(b"\x89PNG")
        return "https://files.example.test/avatar.png"

    monkeypatch.setattr(avatar_upload, "upload_image_to_external_host", fake_upload)

    response = signed_in_client.post(
        "/api/v1/account/avatar-upload",
        files={"file": ("avatar.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["avatar_url"] == "https://files.example.test/avatar.png"


def test_avatar_upload_requires_sign_in(client):
    response = client.post(
        "/api/v1/account/avatar-upload",
        files={"file": ("avatar.png", BytesIO(TINY_PNG), "image/png")},
    )
    assert response.status_code == 401
