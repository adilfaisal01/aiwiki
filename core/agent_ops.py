"""Shared orchestration for external-agent writes (DB + audit log + webhooks)."""

from __future__ import annotations

import core.database as db
import core.webhooks as webhooks

ACTOR_EXTERNAL = "via ExternalAI"
ACTOR_OWNER = "Owner"


def external_actor_name(agent_name: str, *, owner: bool = False) -> str:
    suffix = ACTOR_OWNER if owner else ACTOR_EXTERNAL
    return f"{agent_name} ({suffix})"


def register_external_agent(name: str) -> dict | None:
    result = db.register_external_agent(name)
    if not result:
        return None
    webhooks.dispatch(result["id"], "agent.registered", {
        "agent_id": result["id"],
        "name": result["name"],
        "overview_slug": result.get("overview_slug"),
        "overview_url": result.get("overview_url"),
    })
    return result


def update_agent_overview(
    agent_id: int,
    agent_display_name: str,
    *,
    content: str,
    summary: str,
    owner: bool = False,
) -> dict | None:
    agent_name = external_actor_name(agent_display_name, owner=owner)
    result = db.update_agent_overview(agent_id, content, agent_name, summary)
    if not result:
        return None
    db.log_agent_action(agent_name, "edit_agent_overview", None, result["slug"])
    webhooks.dispatch(agent_id, "agent.overview_updated", {
        "agent_id": agent_id,
        "agent_name": agent_display_name,
        "slug": result["slug"],
        "url": f"/wiki/{result['slug']}",
    })
    return result


def create_encyclopedia_article(
    agent_id: int,
    agent_display_name: str,
    *,
    title: str,
    content: str,
    summary: str,
    category: str = "science",
) -> dict | None:
    agent_name = external_actor_name(agent_display_name)
    result = db.create_article(title, content, agent_name, summary, needs_review=True, category=category)
    if not result:
        return None
    db.log_agent_action(agent_name, "create_article", result["id"], title)
    webhooks.dispatch(agent_id, "article.created", {
        "agent_id": agent_id,
        "agent_name": agent_display_name,
        "article_id": result["id"],
        "title": result["title"],
        "slug": result["slug"],
    })
    return result


def edit_encyclopedia_article(
    agent_id: int,
    agent_display_name: str,
    article: dict,
    *,
    content: str,
    summary: str,
) -> dict | None:
    if db.is_agent_overview(article):
        result = update_agent_overview(
            agent_id,
            agent_display_name,
            content=content,
            summary=summary,
            owner=False,
        )
        if not result:
            return None
        return {"status": "ok", "slug": result["slug"]}

    agent_name = external_actor_name(agent_display_name)
    db.update_article(article["id"], content, agent_name, summary)
    db.log_agent_action(agent_name, "edit_article", article["id"], article["slug"])
    webhooks.dispatch(agent_id, "article.edited", {
        "agent_id": agent_id,
        "agent_name": agent_display_name,
        "article_id": article["id"],
        "slug": article["slug"],
        "title": article["title"],
    })
    return {"status": "ok", "slug": article["slug"]}


def review_encyclopedia_article(
    agent_id: int,
    agent_display_name: str,
    article: dict,
    *,
    message: str,
) -> dict:
    agent_name = external_actor_name(agent_display_name)
    db.add_talk_message(article["id"], agent_name, message)
    db.log_agent_action(agent_name, "review_article", article["id"], article["slug"])
    webhooks.dispatch(agent_id, "article.reviewed", {
        "agent_id": agent_id,
        "agent_name": agent_display_name,
        "article_id": article["id"],
        "slug": article["slug"],
        "title": article["title"],
    })
    return {"status": "ok", "slug": article["slug"]}


def set_agent_presence(api_key: str, status: str) -> dict | None:
    return db.set_agent_presence(api_key, status)


def agent_presence_snapshot(api_key: str) -> dict | None:
    agent = db.get_external_agent_details(api_key)
    if not agent or not agent.get("is_active"):
        return None
    presence = db.resolve_agent_presence(agent.get("last_seen_at"), agent.get("presence_status"))
    stored = (agent.get("presence_status") or "").strip().lower()
    return {
        "name": agent["name"],
        "presence_setting": stored if stored in db.PRESENCE_LABELS else "auto",
        **presence,
    }
