def test_agent_presence_manual(client):
    import uuid
    name = f"PresenceBot{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/v1/register", json={"name": name})
    api_key = reg.json()["api_key"]

    set_afk = client.post(
        "/manage-agents/presence",
        json={"api_key": api_key, "status": "afk"},
    )
    assert set_afk.status_code == 200
    assert set_afk.json()["presence"] == "afk"
    assert set_afk.json()["presence_label"] == "AFK"

    status = client.get("/api/v1/agents/status")
    agent = next(a for a in status.json()["agents"] if a["name"] == name)
    assert agent["presence"] == "afk"
    assert agent["online"] is False

    set_active = client.post(
        "/api/v1/agent/presence",
        headers={"X-API-Key": api_key},
        json={"status": "active"},
    )
    assert set_active.status_code == 200
    assert set_active.json()["presence"] == "active"

    reset = client.post(
        "/manage-agents/presence",
        json={"api_key": api_key, "status": "auto"},
    )
    assert reset.status_code == 200
    assert reset.json()["presence_mode"] == "auto"


def test_presence_invalid_status(client):
    import uuid
    reg = client.post("/api/v1/register", json={"name": f"BadPresence{uuid.uuid4().hex[:8]}"})
    api_key = reg.json()["api_key"]
    bad = client.post(
        "/manage-agents/presence",
        json={"api_key": api_key, "status": "sleeping"},
    )
    assert bad.status_code == 400
