"""Execute AITool invokes using metadata stored on the article."""

from __future__ import annotations

from typing import Any

import aitools.server_tools  # noqa: F401 — register builtin handlers
from aitools.server_tools import execute_builtin_handler, has_builtin_handler
from wiki.article_blueprint import ToolSpec
from aitools.tool_spec import parse_tool_spec


async def execute_server_tool(article: dict, body: dict[str, Any]) -> dict[str, Any]:
    spec = parse_tool_spec(article)
    if spec.execution != "server":
        raise ValueError("Tool is not configured for server execution")
    handler_id = (spec.server_handler or "").strip()
    if not handler_id:
        raise KeyError("Tool has no server_handler configured")
    if not has_builtin_handler(handler_id):
        raise KeyError(f"Unknown server handler: {handler_id}")
    return await execute_builtin_handler(handler_id, body, config=spec.server_config)


def validate_tool_spec_for_publish(spec: ToolSpec) -> None:
    if spec.execution == "server" and not has_builtin_handler(spec.server_handler or ""):
        raise ValueError(f"Unknown server handler: {spec.server_handler}")
