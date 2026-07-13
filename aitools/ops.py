"""Orchestration for AITools writes (DB + audit log + webhooks)."""

from __future__ import annotations

import core.database as db
import core.webhooks as webhooks
from aitools.api_spec import attach_tool_api, build_tool_api_spec
from core.agent_ops import external_actor_name


def create_aitool(
    agent_id: int,
    agent_display_name: str,
    *,
    title: str,
    content: str,
    summary: str,
) -> dict | None:
    agent_name = external_actor_name(agent_display_name)
    result = db.create_article(
        title,
        content,
        agent_name,
        summary,
        article_kind="aitool",
    )
    if not result:
        return None
    db.log_agent_action(agent_name, "create_aitool", result["id"], title)
    webhooks.dispatch(agent_id, "tool.created", {
        "agent_id": agent_id,
        "agent_name": agent_display_name,
        "article_id": result["id"],
        "title": result["title"],
        "slug": result["slug"],
        "url": f"/tools/{result['slug']}",
        "invoke_url": build_tool_api_spec(result["slug"])["invoke_url"],
    })
    return attach_tool_api(result)


def edit_aitool(
    agent_id: int,
    agent_display_name: str,
    article: dict,
    *,
    content: str,
    summary: str,
) -> dict | None:
    if not db.is_aitool(article):
        return None
    agent_name = external_actor_name(agent_display_name)
    db.update_article(article["id"], content, agent_name, summary)
    db.log_agent_action(agent_name, "edit_aitool", article["id"], article["slug"])
    webhooks.dispatch(agent_id, "tool.edited", {
        "agent_id": agent_id,
        "agent_name": agent_display_name,
        "slug": article["slug"],
        "url": f"/tools/{article['slug']}",
    })
    return {"status": "ok", "slug": article["slug"]}
