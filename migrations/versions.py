from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import database as db


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    up: Callable


def _migration_001_initial(conn) -> None:
    """Baseline marker for databases created before the migration runner existed."""
    p = db._param_style()
    row = db._fetchone(conn, "SELECT version FROM schema_version LIMIT 1")
    if not row:
        db._execute(conn, f"INSERT INTO schema_version (version) VALUES ({p})", (1,))


def _migration_002_article_ownership(conn) -> None:
    if not db._column_exists(conn, "articles", "article_kind"):
        db._execute(
            conn,
            "ALTER TABLE articles ADD COLUMN article_kind TEXT NOT NULL DEFAULT 'encyclopedia'",
        )
    if not db._column_exists(conn, "articles", "owner_agent_id"):
        db._execute(conn, "ALTER TABLE articles ADD COLUMN owner_agent_id INTEGER")


def _migration_003_external_agents_last_seen(conn) -> None:
    if not db._column_exists(conn, "external_agents", "last_seen_at"):
        db._execute(conn, "ALTER TABLE external_agents ADD COLUMN last_seen_at TEXT")


def _migration_004_external_agents_overview(conn) -> None:
    if not db._column_exists(conn, "external_agents", "overview_article_id"):
        db._execute(conn, "ALTER TABLE external_agents ADD COLUMN overview_article_id INTEGER")


def _migration_005_external_agents_webhook(conn) -> None:
    if not db._column_exists(conn, "external_agents", "webhook_url"):
        db._execute(conn, "ALTER TABLE external_agents ADD COLUMN webhook_url TEXT")


def _migration_006_backfill_agent_overviews(conn) -> None:
    db.backfill_agent_overviews(conn)


def _migration_007_agent_presence_status(conn) -> None:
    if not db._column_exists(conn, "external_agents", "presence_status"):
        db._execute(conn, "ALTER TABLE external_agents ADD COLUMN presence_status TEXT")


MIGRATIONS: list[Migration] = [
    Migration(1, "initial_baseline", _migration_001_initial),
    Migration(2, "article_ownership_columns", _migration_002_article_ownership),
    Migration(3, "external_agents_last_seen", _migration_003_external_agents_last_seen),
    Migration(4, "external_agents_overview_link", _migration_004_external_agents_overview),
    Migration(5, "external_agents_webhook", _migration_005_external_agents_webhook),
    Migration(6, "backfill_agent_overviews", _migration_006_backfill_agent_overviews),
    Migration(7, "agent_presence_status", _migration_007_agent_presence_status),
]

CURRENT_VERSION = MIGRATIONS[-1].version

MIGRATION_NAMES = {m.version: m.name for m in MIGRATIONS}
