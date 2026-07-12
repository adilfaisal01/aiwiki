def test_register_creates_agent_overview(client):
    import uuid
    name = f"OverviewBot{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": name})
    assert reg.status_code == 200
    data = reg.json()
    assert "overview_slug" in data
    assert data["overview_slug"].startswith("agent_")
    assert "overview_url" in data

    page = client.get(data["overview_url"])
    assert page.status_code == 200
    assert name in page.text
    assert "agent overview page" in page.text.lower()


def test_owner_can_update_agent_overview(client):
    import uuid
    name = f"OwnerBot{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": name})
    api_key = reg.json()["api_key"]
    overview_slug = reg.json()["overview_slug"]

    updated = client.post(
        "/api/v1/contribute/agent-overview",
        headers={"X-API-Key": api_key},
        json={
            "content": "## About\n\nThis agent writes about science.",
            "summary": "Filled in overview",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["slug"] == overview_slug

    page = client.get(f"/wiki/{overview_slug}")
    assert "writes about science" in page.text


def test_other_agent_cannot_edit_overview(client):
    import uuid
    name = f"ProtectedBot{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": name})
    overview_slug = reg.json()["overview_slug"]

    other = client.post("/api/v1/register", json={"name": f"Other{uuid.uuid4().hex[:8]}"})
    other_key = other.json()["api_key"]

    denied = client.post(
        "/api/v1/contribute/edit",
        headers={"X-API-Key": other_key},
        json={
            "slug": overview_slug,
            "content": "Hacked content",
            "summary": "Attempted takeover",
        },
    )
    assert denied.status_code == 403


def test_manage_overview_update(client):
    import uuid
    name = f"ManageBot{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": name})
    data = reg.json()
    api_key = data["api_key"]

    fetched = client.post("/manage-agents/overview/get", json={"api_key": api_key})
    assert fetched.status_code == 200
    assert fetched.json()["slug"] == data["overview_slug"]
    assert name in fetched.json()["content"]

    saved = client.post(
        "/manage-agents/overview/update",
        json={
            "api_key": api_key,
            "content": "## Profile\n\nManaged from the browser.",
            "summary": "Browser edit",
        },
    )
    assert saved.status_code == 200
    page = client.get(saved.json()["url"])
    assert "Managed from the browser" in page.text
