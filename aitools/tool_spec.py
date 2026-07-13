"""Helpers for tool_spec_json stored on aitool articles."""

from __future__ import annotations

from typing import Any

from wiki.article_blueprint import ToolSpec

DEFAULT_TOOL_SPEC = ToolSpec()


def tool_spec_from_json(raw: str | None) -> ToolSpec:
    if not raw:
        return DEFAULT_TOOL_SPEC
    try:
        return ToolSpec.model_validate_json(raw)
    except Exception:
        return DEFAULT_TOOL_SPEC


def tool_spec_to_json(spec: ToolSpec | None) -> str | None:
    if spec is None:
        return None
    return spec.model_dump_json(exclude_none=True)


def tool_spec_from_blueprint(blueprint_tool: ToolSpec | None) -> str | None:
    if blueprint_tool is None:
        return tool_spec_to_json(DEFAULT_TOOL_SPEC)
    return tool_spec_to_json(blueprint_tool)


def parse_tool_spec(article: dict | None) -> ToolSpec:
    if not article:
        return DEFAULT_TOOL_SPEC
    raw = article.get("tool_spec_json")
    if raw is None:
        return DEFAULT_TOOL_SPEC
    if isinstance(raw, dict):
        try:
            return ToolSpec.model_validate(raw)
        except Exception:
            return DEFAULT_TOOL_SPEC
    return tool_spec_from_json(str(raw))


def tool_execution_mode(article: dict) -> str:
    return parse_tool_spec(article).execution


def invoke_example_for(article: dict) -> dict[str, Any] | None:
    return parse_tool_spec(article).invoke_example
