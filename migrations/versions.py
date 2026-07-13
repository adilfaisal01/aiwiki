from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import core.database as db


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


def _migration_008_users(conn) -> None:
    if not db._table_exists(conn, "users"):
        db._execute(
            conn,
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                session_token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """,
        )


def _migration_009_user_avatar_url(conn) -> None:
    if not db._column_exists(conn, "users", "avatar_url"):
        db._execute(conn, "ALTER TABLE users ADD COLUMN avatar_url TEXT")


def _migration_010_user_email_password(conn) -> None:
    if not db._column_exists(conn, "users", "email"):
        db._execute(conn, "ALTER TABLE users ADD COLUMN email TEXT")
    if not db._column_exists(conn, "users", "password_hash"):
        db._execute(conn, "ALTER TABLE users ADD COLUMN password_hash TEXT")
    db._execute(conn, "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")


def _migration_011_external_agents_user_id(conn) -> None:
    if not db._column_exists(conn, "external_agents", "user_id"):
        db._execute(conn, "ALTER TABLE external_agents ADD COLUMN user_id TEXT")
    db._execute(conn, "CREATE INDEX IF NOT EXISTS idx_external_agents_user_id ON external_agents(user_id)")


def _migration_012_user_locale(conn) -> None:
    if not db._column_exists(conn, "users", "locale"):
        db._execute(conn, "ALTER TABLE users ADD COLUMN locale TEXT")


def _migration_013_builtin_agents(conn) -> None:
    from core import config

    if not db._table_exists(conn, "builtin_agents"):
        sid = "SERIAL PRIMARY KEY" if config.is_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
        db._execute(
            conn,
            f"""
            CREATE TABLE builtin_agents (
                id {sid},
                name TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT,
                last_action TEXT,
                last_action_at TEXT,
                overview_article_id INTEGER
            )
            """,
        )
    db.seed_builtin_agents(conn)


MIGRATIONS: list[Migration] = [
    Migration(1, "initial_baseline", _migration_001_initial),
    Migration(2, "article_ownership_columns", _migration_002_article_ownership),
    Migration(3, "external_agents_last_seen", _migration_003_external_agents_last_seen),
    Migration(4, "external_agents_overview_link", _migration_004_external_agents_overview),
    Migration(5, "external_agents_webhook", _migration_005_external_agents_webhook),
    Migration(6, "backfill_agent_overviews", _migration_006_backfill_agent_overviews),
    Migration(7, "agent_presence_status", _migration_007_agent_presence_status),
    Migration(8, "users", _migration_008_users),
    Migration(9, "user_avatar_url", _migration_009_user_avatar_url),
    Migration(10, "user_email_password", _migration_010_user_email_password),
    Migration(11, "external_agents_user_id", _migration_011_external_agents_user_id),
    Migration(12, "user_locale", _migration_012_user_locale),
    Migration(13, "builtin_agents", _migration_013_builtin_agents),
]

CURRENT_VERSION = MIGRATIONS[-1].version

MIGRATION_NAMES = {m.version: m.name for m in MIGRATIONS}
