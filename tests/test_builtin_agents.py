from core.builtin_agents import BUILTIN_AGENTS


def test_agents_status_includes_builtin_agents(client):
    response = client.get("/api/v1/agents/status")
    assert response.status_code == 200
    data = response.json()
    names = {agent["name"] for agent in data["agents"]}
    for agent in BUILTIN_AGENTS:
        assert agent["name"] in names

    builtin = [a for a in data["agents"] if a.get("builtin")]
    assert len(builtin) == len(BUILTIN_AGENTS)
    assert all(item["presence"] == "active" for item in builtin)
    assert all(item.get("overview_url") for item in builtin)


def test_home_about_lists_named_agents(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Coordinator Kai" in response.text
    assert "Critic Carla" in response.text
    assert "Quality Improver Quinn" in response.text
