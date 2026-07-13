from aitools.api_spec import attach_tool_api, build_tool_api_spec


def test_build_tool_api_spec_paths():
    spec = build_tool_api_spec("text_uppercase", public_base_url="http://127.0.0.1:8001")
    assert spec["slug"] == "text_uppercase"
    assert spec["get_path"] == "/api/v1/tool/text_uppercase"
    assert spec["invoke_path"] == "/api/v1/tool/text_uppercase/invoke"
    assert spec["invoke_url"] == "http://127.0.0.1:8001/api/v1/tool/text_uppercase/invoke"
    assert "curl -X POST" in spec["curl_invoke"]


def test_attach_tool_api():
    payload = attach_tool_api({"id": 1, "title": "Demo", "slug": "demo"})
    assert "api" in payload
    assert payload["api"]["get_path"] == "/api/v1/tool/demo"
