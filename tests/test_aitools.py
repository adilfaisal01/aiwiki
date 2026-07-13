import core.database as db


def _register_agent(client, name: str) -> str:
    response = client.post("/api/v1/register", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["api_key"]


def test_tools_portal_and_isolation(client):
    response = client.get("/tools")
    assert response.status_code == 200
    assert "Welcome to AITools" in response.text
    assert "Welcome to AIWiki" not in response.text.split("portal-welcome")[1].split("portal-announcements")[0]
    assert "Tool of the day" in response.text
    assert "Featured tools" in response.text
    assert "AIWiki MCP server" in response.text
    assert "portal-grid-aotd" in response.text
    assert "home-article-of-day" not in response.text
    assert "Featured articles" not in response.text.split("portal-grid")[1]

    api_key = _register_agent(client, "ToolPublisher")
    create = client.post(
        "/api/v1/contribute/tool",
        headers={"X-API-Key": api_key},
        json={
            "title": "Uppercase Helper",
            "content": (
                "Converts text to uppercase locally.\n\n"
                "```python\n"
                "def run(text: str) -> str:\n"
                "    return text.upper()\n"
                "```"
            ),
            "summary": "Initial tool version",
        },
    )
    assert create.status_code == 200, create.text
    slug = create.json()["slug"]
    assert create.json()["api"]["invoke_path"] == f"/api/v1/tool/{slug}/invoke"

    tool_page = client.get(f"/tools/{slug}")
    assert tool_page.status_code == 200
    assert "Uppercase Helper" in tool_page.text
    assert "Tool API" in tool_page.text
    assert f"/api/v1/tool/{slug}/invoke" in tool_page.text
    assert "tool-article-body" in tool_page.text
    assert "Converts text to uppercase locally" in tool_page.text
    assert 'class="codehilite"' in tool_page.text
    assert 'class="nf">run</span>' in tool_page.text

    wiki_page = client.get(f"/wiki/{slug}")
    assert wiki_page.status_code == 404

    search = client.get("/search", params={"q": "Uppercase", "scope": "tools"})
    assert search.status_code == 200
    assert f"/tools/{slug}" in search.text

    listing = client.get("/api/v1/tools")
    assert listing.status_code == 200
    assert any(item["slug"] == slug for item in listing.json())

    invoke = client.post(
        f"/api/v1/tool/{slug}/invoke",
        headers={"X-API-Key": api_key},
    )
    assert invoke.status_code == 200
    payload = invoke.json()
    assert payload["execution"] == "client"
    assert "def run" in payload["content"]

    edit = client.post(
        "/api/v1/contribute/tool-edit",
        headers={"X-API-Key": api_key},
        json={
            "slug": slug,
            "content": "def run(text):\n    return text.lower()",
            "summary": "Lowercase instead",
        },
    )
    assert edit.status_code == 200, edit.text

    wiki_edit = client.post(
        "/api/v1/contribute/edit",
        headers={"X-API-Key": api_key},
        json={"slug": slug, "content": "nope", "summary": "wrong api"},
    )
    assert wiki_edit.status_code == 404

    recent = client.get("/tools/recent-changes")
    assert recent.status_code == 200
    assert "Uppercase Helper" in recent.text

    assert db.is_aitool(db.get_article(slug))


def test_get_tool_blueprint_endpoint(client):
    response = client.get("/api/v1/tool-blueprint")
    assert response.status_code == 200
    data = response.json()
    assert data["reference_slug"] == "text_uppercase"
    assert "schema" in data
    assert "example" in data
    assert data["example"]["infobox"] is not None


def test_contribute_tool_with_blueprint(client):
    from wiki.article_blueprint import example_tool_blueprint

    api_key = _register_agent(client, "ToolBlueprintBot")
    blueprint = example_tool_blueprint().model_dump(mode="json")
    blueprint["infobox"]["title"] = "JSON Formatter"
    blueprint["lead"] = ["The <b>JSON Formatter</b> pretty-prints JSON on the client."]

    create = client.post(
        "/api/v1/contribute/tool",
        headers={"X-API-Key": api_key},
        json={
            "title": "JSON Formatter",
            "summary": "Created via tool blueprint",
            "blueprint": blueprint,
        },
    )
    assert create.status_code == 200, create.text
    slug = create.json()["slug"]

    tool_page = client.get(f"/tools/{slug}")
    assert tool_page.status_code == 200
    assert "JSON Formatter" in tool_page.text
    assert 'class="infobox"' in tool_page.text
    assert 'class="infobox-title"' in tool_page.text
    assert "Client-side" in tool_page.text
    assert "<img" in tool_page.text


def test_contribute_tool_edit_with_blueprint(client):
    from wiki.article_blueprint import BlueprintSection, Infobox, InfoboxEntry, example_tool_blueprint

    api_key = _register_agent(client, "ToolBlueprintEditor")
    blueprint = example_tool_blueprint().model_dump(mode="json")
    blueprint["infobox"]["title"] = "Slugify Text"
    blueprint["lead"] = ["Slugifies text on the client."]

    create = client.post(
        "/api/v1/contribute/tool",
        headers={"X-API-Key": api_key},
        json={
            "title": "Slugify Text",
            "summary": "Initial",
            "blueprint": blueprint,
        },
    )
    assert create.status_code == 200
    slug = create.json()["slug"]

    updated = example_tool_blueprint()
    updated.infobox = Infobox(
        title="Slugify Text",
        rows=[InfoboxEntry(kind="field", label="Runtime", value="Client-side (updated)")],
    )
    updated.lead = ["Updated slugify tool."]
    updated.sections = [
        BlueprintSection(
            title="Implementation",
            code_blocks=updated.sections[0].code_blocks,
        )
    ]

    edit = client.post(
        "/api/v1/contribute/tool-edit",
        headers={"X-API-Key": api_key},
        json={
            "slug": slug,
            "summary": "Updated infobox",
            "blueprint": updated.model_dump(mode="json"),
        },
    )
    assert edit.status_code == 200, edit.text

    tool_page = client.get(f"/tools/{slug}")
    assert tool_page.status_code == 200
    assert "Client-side (updated)" in tool_page.text
