"""Account usage summary for settings (stub until billing enforcement)."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone

import core.database as db
from web.i18n import t

PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "free": {"server_invokes": 100, "agents": 1},
    "payg": {"server_invokes": None, "agents": 3},
    "pro": {"server_invokes": 5000, "agents": 10},
    "team": {"server_invokes": 50000, "agents": None},
}

PAYG_RATE_EUR = 0.005


def _current_billing_period() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    last_day = monthrange(now.year, now.month)[1]
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=0)
    return start.date().isoformat(), end.date().isoformat()


def _user_plan_id(user_id: str) -> str:
    """Return the user's plan. Defaults to free until billing is persisted."""
    _ = user_id
    return "free"


def account_usage_summary(user: dict, locale: str) -> dict:
    plan_id = _user_plan_id(user["id"])
    limits = PLAN_LIMITS.get(plan_id, PLAN_LIMITS["free"])
    agents = db.get_external_agents_by_user_id(user["id"])
    agent_count = len(agents)
    server_used = db.get_server_invoke_count(user["id"])
    period_start, period_end = _current_billing_period()

    server_limit = limits["server_invokes"]
    agent_limit = limits["agents"]

    payload: dict = {
        "plan": plan_id,
        "plan_label": t(locale, f"pricing.plan.{plan_id}.name"),
        "period_start": period_start,
        "period_end": period_end,
        "server_invokes": {
            "used": server_used,
            "limit": server_limit,
            "unlimited": server_limit is None,
            "usage_based": plan_id == "payg",
        },
        "registered_agents": {
            "used": agent_count,
            "limit": agent_limit,
            "unlimited": agent_limit is None,
        },
        "client_tool_invokes": {"unlimited": True},
    }

    if plan_id == "payg":
        payload["estimated_cost_eur"] = round(server_used * PAYG_RATE_EUR, 4)

    return payload
