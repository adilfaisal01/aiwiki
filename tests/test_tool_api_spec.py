from aitools.api_spec import attach_tool_api, build_tool_api_spec


def test_build_tool_api_spec_paths():
    article = {
        "slug": "text_uppercase",
        "tool_spec_json": '{"execution":"client"}',
    }
    spec = build_tool_api_spec(article, public_base_url="http://127.0.0.1:8001")
    assert spec["slug"] == "text_uppercase"
    assert spec["execution"] == "client"
    assert spec["get_path"] == "/api/v1/tool/text_uppercase"
    assert spec["invoke_path"] == "/api/v1/tool/text_uppercase/invoke"
    assert spec["invoke_url"] == "http://127.0.0.1:8001/api/v1/tool/text_uppercase/invoke"
    assert "curl -X POST" in spec["curl_invoke"]


def test_build_tool_api_spec_server_tool():
    article = {
        "slug": "web_search",
        "tool_spec_json": (
            '{"execution":"server","server_handler":"web_search",'
            '"invoke_example":{"query":"test","limit":3}}'
        ),
    }
    spec = build_tool_api_spec(article, public_base_url="http://127.0.0.1:8001")
    assert spec["execution"] == "server"
    assert spec["server_handler"] == "web_search"
    assert spec["invoke_body"] == {"query": "test", "limit": 3}


def test_attach_tool_api():
    article = {"slug": "demo", "tool_spec_json": '{"execution":"client"}'}
    payload = attach_tool_api({"id": 1, "title": "Demo", "slug": "demo"}, article=article)
    assert "api" in payload
    assert payload["api"]["get_path"] == "/api/v1/tool/demo"
