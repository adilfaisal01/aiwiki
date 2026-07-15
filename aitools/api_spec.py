"""Per-tool API endpoints derived from article metadata at create/read time."""

from __future__ import annotations

import json

from core import config
from aitools.tool_spec import invoke_example_for, parse_tool_spec, tool_execution_mode


def build_tool_api_spec(article: dict, *, public_base_url: str | None = None) -> dict:
    slug = article["slug"]
    base = (public_base_url or config.PUBLIC_BASE_URL).rstrip("/")
    get_path = f"/api/v1/tool/{slug}"
    invoke_path = f"/api/v1/tool/{slug}/invoke"
    get_url = f"{base}{get_path}"
    invoke_url = f"{base}{invoke_path}"
    execution = tool_execution_mode(article)
    invoke_body = invoke_example_for(article)
    spec = parse_tool_spec(article)
    curl_lines = [
        f'curl -X POST "{invoke_url}" \\',
        '  -H "X-API-Key: YOUR_API_KEY" \\',
        '  -H "Content-Type: application/json"',
    ]
    if invoke_body:
        body_json = json.dumps(invoke_body, ensure_ascii=False)
        curl_lines[-1] += " \\"
        curl_lines.append(f"  -d '{body_json}'")
    return {
        "slug": slug,
        "get_path": get_path,
        "invoke_path": invoke_path,
        "get_url": get_url,
        "invoke_url": invoke_url,
        "execution": execution,
        "server_handler": spec.server_handler,
        "invoke_body": invoke_body,
        "curl_get": f'curl "{get_url}"',
        "curl_invoke": "\n".join(curl_lines),
    }


def attach_tool_api(payload: dict, *, article: dict | None = None) -> dict:
    slug = payload.get("slug")
    if not slug:
        return payload
    source = article if article is not None else payload
    if "slug" not in source:
        source = {**payload, "slug": slug}
    return {**payload, "api": build_tool_api_spec(source)}
