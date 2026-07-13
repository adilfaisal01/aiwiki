"""Per-tool API endpoints derived from slug at create/read time."""

from __future__ import annotations

from core import config


def build_tool_api_spec(slug: str, *, public_base_url: str | None = None) -> dict:
    base = (public_base_url or config.PUBLIC_BASE_URL).rstrip("/")
    get_path = f"/api/v1/tool/{slug}"
    invoke_path = f"/api/v1/tool/{slug}/invoke"
    get_url = f"{base}{get_path}"
    invoke_url = f"{base}{invoke_path}"
    return {
        "slug": slug,
        "get_path": get_path,
        "invoke_path": invoke_path,
        "get_url": get_url,
        "invoke_url": invoke_url,
        "curl_get": f'curl "{get_url}"',
        "curl_invoke": (
            f'curl -X POST "{invoke_url}" \\\n'
            f'  -H "X-API-Key: YOUR_API_KEY" \\\n'
            f'  -H "Content-Type: application/json"'
        ),
    }


def attach_tool_api(payload: dict) -> dict:
    slug = payload.get("slug")
    if not slug:
        return payload
    return {**payload, "api": build_tool_api_spec(slug)}
