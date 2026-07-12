def test_search_articles(client):
    import uuid
    title = f"SearchTarget{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": f"SearchBot{uuid.uuid4().hex[:8]}"})
    api_key = reg.json()["api_key"]
    client.post(
        "/api/v1/contribute/article",
        headers={"X-API-Key": api_key},
        json={"title": title, "content": "Unique searchable phrase xyzzy", "summary": "s"},
    )

    api = client.get("/api/v1/search", params={"q": "xyzzy"})
    assert api.status_code == 200
    assert len(api.json()["results"]) >= 1

    page = client.get("/search", params={"q": "xyzzy"})
    assert page.status_code == 200
    assert "xyzzy" in page.text.lower()


def test_check_article_title(client):
    import uuid
    title = f"CheckTitle{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": f"CheckBot{uuid.uuid4().hex[:8]}"})
    api_key = reg.json()["api_key"]
    client.post(
        "/api/v1/contribute/article",
        headers={"X-API-Key": api_key},
        json={"title": title, "content": "Body", "summary": "s"},
    )

    missing = client.get("/api/v1/articles/check", params={"title": f"Other{uuid.uuid4().hex[:8]}"})
    assert missing.status_code == 200
    assert missing.json()["exists"] is False

    exists = client.get("/api/v1/articles/check", params={"title": title})
    assert exists.status_code == 200
    assert exists.json()["exists"] is True


def test_agent_activity_and_webhook(client, monkeypatch):
    import uuid

    events = []

    def fake_dispatch(agent_id, event, payload):
        events.append({"agent_id": agent_id, "event": event, "payload": payload})

    monkeypatch.setattr("external_api.routes.webhooks.dispatch", fake_dispatch)

    name = f"HookBot{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": name})
    data = reg.json()
    api_key = data["api_key"]
    assert any(e["event"] == "agent.registered" for e in events)

    client.post(
        "/api/v1/agent/webhook",
        headers={"X-API-Key": api_key},
        json={"url": "https://example.com/hook"},
    )
    hook = client.get("/api/v1/agent/webhook", headers={"X-API-Key": api_key})
    assert hook.json()["webhook_url"] == "https://example.com/hook"

    client.post(
        "/api/v1/contribute/article",
        headers={"X-API-Key": api_key},
        json={"title": f"HookArt{uuid.uuid4().hex[:8]}", "content": "Hook test", "summary": "s"},
    )
    assert any(e["event"] == "article.created" for e in events)

    activity = client.get(f"/api/v1/agents/{name}/activity")
    assert activity.status_code == 200
    assert len(activity.json()["activity"]) >= 1

    own = client.get("/api/v1/agent/activity", headers={"X-API-Key": api_key})
    assert own.status_code == 200


def test_health_extended(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "database_latency_ms" in data
    assert "rate_limit_backend" in data
    assert data["rate_limit_backend"] in ("memory", "redis")
    assert "agent_loop" in data
    assert data["agent_loop"]["enabled"] is False


def test_encyclopedia_articles_exclude_overviews(client):
    import uuid
    import database as db

    name = f"IndexBot{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": name})
    overview_slug = reg.json()["overview_slug"]

    slugs = [a["slug"] for a in db.get_encyclopedia_articles()]
    assert overview_slug not in slugs

    page = client.get("/")
    assert page.status_code == 200
    assert "Registered agents" in page.text
    assert name in page.text


def test_static_cache_headers(client):
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert "max-age=" in response.headers.get("cache-control", "")


def test_static_asset_cache_busting(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert "/static/style.css?v=" in response.text
    assert "/static/live_updates.js?v=" in response.text
    assert 'name="aiwiki-static-version"' in response.text


def test_live_version_endpoint(client):
    response = client.get("/api/v1/live/version")
    assert response.status_code == 200
    assert "no-store" in response.headers.get("cache-control", "")
    data = response.json()
    assert data["static_version"]


def test_live_home_endpoint(client):
    response = client.get("/api/v1/live/home")
    assert response.status_code == 200
    data = response.json()
    assert "static_version" in data
    assert "featured_articles" in data
    assert "recent_changes" in data
    assert "registered_agents" in data


def test_csp_nonce_on_page(client):
    response = client.get("/")
    csp = response.headers.get("content-security-policy", "")
    assert "nonce-" in csp
    assert 'nonce="' in response.text or "nonce='" in response.text
