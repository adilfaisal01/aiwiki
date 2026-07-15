import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import core.database as db
from aitools.server_tools import _parse_ddg_html, run_web_search, search_web
from aitools.tool_spec import parse_tool_spec, tool_execution_mode
from wiki.article_blueprint import ToolSpec


def test_tool_execution_mode_from_article():
    client_article = {"slug": "text_uppercase", "tool_spec_json": '{"execution":"client"}'}
    server_article = {
        "slug": "web_search",
        "tool_spec_json": '{"execution":"server","server_handler":"web_search"}',
    }
    assert tool_execution_mode(client_article) == "client"
    assert tool_execution_mode(server_article) == "server"


def test_parse_ddg_html_extracts_results():
    html_page = """
    <a class="result__a" href="https://example.com/a">Alpha Site</a>
    <a class="result__snippet" href="https://example.com/a">First snippet text</a>
    <a class="result__a" href="https://example.com/b">Beta Site</a>
    <a class="result__snippet" href="https://example.com/b">Second snippet</a>
    """
    results = _parse_ddg_html(html_page, 5)
    assert len(results) == 2
    assert results[0]["title"] == "Alpha Site"
    assert results[0]["url"] == "https://example.com/a"
    assert "First snippet" in results[0]["snippet"]


def test_run_web_search_requires_query():
    with pytest.raises(ValueError, match="query"):
        asyncio.run(run_web_search({}, {}))


def test_run_web_search_returns_results():
    sample = [
        {"title": "FastAPI", "url": "https://fastapi.tiangolo.com/", "snippet": "Modern Python web framework"},
    ]
    with patch("aitools.server_tools.search_web", new=AsyncMock(return_value=sample)):
        payload = asyncio.run(run_web_search({"query": "FastAPI", "limit": 3}, {}))
    assert payload["query"] == "FastAPI"
    assert payload["count"] == 1
    assert payload["results"][0]["title"] == "FastAPI"


def test_web_search_invoke_api(client):
    register = client.post("/api/v1/register", json={"name": "WebSearchTester"})
    assert register.status_code == 200
    api_key = register.json()["api_key"]

    sample = [
        {"title": "Python", "url": "https://python.org/", "snippet": "Official site"},
    ]
    with patch("aitools.server_tools.search_web", new=AsyncMock(return_value=sample)):
        response = client.post(
            "/api/v1/tool/web_search/invoke",
            headers={"X-API-Key": api_key},
            json={"query": "Python programming", "limit": 3},
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["execution"] == "server"
    assert data["result"]["count"] == 1
    assert data["result"]["results"][0]["title"] == "Python"


def test_web_search_seed_article_has_tool_spec(client):
    article = db.get_article("web_search")
    assert article is not None
    spec = parse_tool_spec(article)
    assert spec.execution == "server"
    assert spec.server_handler == "web_search"
    assert spec.invoke_example is not None


def test_web_search_tool_page(client):
    page = client.get("/tools/web_search")
    assert page.status_code == 200
    assert "Web Search" in page.text
    assert "Server-side" in page.text
    assert "QuBrain" in page.text
    assert page.text.find('class="infobox"') < page.text.find("tool-api-box")
