def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"


def test_register_and_contribute(client):
    import uuid
    name = f"TestBot{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": name})
    assert reg.status_code == 200
    api_key = reg.json()["api_key"]
    title = f"Test Article {uuid.uuid4().hex[:8]}"

    article = client.post(
        "/api/v1/contribute/article",
        headers={"X-API-Key": api_key},
        json={
            "title": title,
            "content": "## Test\n\nContent here.",
            "summary": "Initial",
        },
    )
    assert article.status_code == 200
    slug = article.json()["slug"]

    page = client.get(f"/wiki/{slug}")
    assert page.status_code == 200
    assert title in page.text
    assert "<script>alert" not in page.text


def test_duplicate_agent_name(client):
    import uuid
    name = f"DupeBot{uuid.uuid4().hex[:8]}"
    client.post("/api/v1/register", json={"name": name})
    dup = client.post("/api/v1/register", json={"name": name})
    assert dup.status_code == 409


def test_agents_status(client):
    import uuid
    name = f"StatusBot{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": name})
    assert reg.status_code == 200

    status = client.get("/api/v1/agents/status")
    assert status.status_code == 200
    data = status.json()
    names = [a["name"] for a in data["agents"]]
    assert name in names
    agent = next(a for a in data["agents"] if a["name"] == name)
    assert agent["online"] is True
