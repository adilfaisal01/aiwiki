"""Shared payloads for AITools portal pages."""

from __future__ import annotations

import core.database as db
from wiki.helpers import build_article_of_day


def tools_portal_data(*, featured_limit: int = 20, recent_limit: int = 8) -> dict:
    tools = db.get_aitools()
    featured = tools[:featured_limit]
    return {
        "tools": featured,
        "tool_count": len(tools),
        "tool_of_day": build_article_of_day(featured),
        "recent_changes": db.get_aitool_recent_changes(recent_limit),
    }


def tools_live_payload(*, featured_limit: int = 20, recent_limit: int = 8) -> dict:
    from web.static_assets import static_version

    data = tools_portal_data(featured_limit=featured_limit, recent_limit=recent_limit)
    return {
        "static_version": static_version(),
        "tool_count": data["tool_count"],
        "tool_of_day": data["tool_of_day"],
        "featured_tools": data["tools"],
        "recent_changes": data["recent_changes"],
    }


def tools_recent_changes_live_payload(*, limit: int = 50) -> dict:
    from web.static_assets import static_version

    return {
        "static_version": static_version(),
        "changes": db.get_aitool_recent_changes(limit),
    }
