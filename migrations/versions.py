from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import core.database as db
import core.config as config


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


# NOTE: migration 8 on prod is "pending_topics" from the old codebase.
# The new migrations (users, accounts, etc.) start at 9 to avoid collision.
# See _migration_017_pending_topics below for the current version.


def _migration_009_users(conn) -> None:
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


def _migration_010_user_avatar_url(conn) -> None:
    if not db._column_exists(conn, "users", "avatar_url"):
        db._execute(conn, "ALTER TABLE users ADD COLUMN avatar_url TEXT")


def _migration_011_user_email_password(conn) -> None:
    if not db._column_exists(conn, "users", "email"):
        db._execute(conn, "ALTER TABLE users ADD COLUMN email TEXT")
    if not db._column_exists(conn, "users", "password_hash"):
        db._execute(conn, "ALTER TABLE users ADD COLUMN password_hash TEXT")
    db._execute(conn, "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")


def _migration_012_external_agents_user_id(conn) -> None:
    if not db._column_exists(conn, "external_agents", "user_id"):
        db._execute(conn, "ALTER TABLE external_agents ADD COLUMN user_id TEXT")
    db._execute(conn, "CREATE INDEX IF NOT EXISTS idx_external_agents_user_id ON external_agents(user_id)")


def _migration_013_user_locale(conn) -> None:
    if not db._column_exists(conn, "users", "locale"):
        db._execute(conn, "ALTER TABLE users ADD COLUMN locale TEXT")


def _migration_014_builtin_agents(conn) -> None:
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


def _migration_015_user_server_invoke_usage(conn) -> None:
    if not db._table_exists(conn, "user_server_invoke_usage"):
        db._execute(
            conn,
            """
            CREATE TABLE user_server_invoke_usage (
                user_id TEXT NOT NULL,
                period TEXT NOT NULL,
                invoke_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, period)
            )
            """,
        )
        db._execute(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_user_server_invoke_usage_period ON user_server_invoke_usage(period)",
        )


def _migration_016_articles_tool_spec(conn) -> None:
    if not db._column_exists(conn, "articles", "tool_spec_json"):
        db._execute(conn, "ALTER TABLE articles ADD COLUMN tool_spec_json TEXT")


def _migration_017_pending_topics(conn) -> None:
    """Create pending_topics table for wiki-linked article generation."""
    if db._table_exists(conn, "pending_topics"):
        return
    sid = (
        "INTEGER PRIMARY KEY AUTOINCREMENT"
        if not config.is_postgres()
        else "INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY"
    )
    db._execute(
        conn,
        f"""CREATE TABLE pending_topics (
            id {sid},
            topic TEXT NOT NULL UNIQUE,
            source_article_id INTEGER,
            category TEXT NOT NULL DEFAULT 'science',
            queued_at TEXT NOT NULL,
            picked_at TEXT
        )""",
    )


def _migration_018_fix_hardcoded_urls(conn) -> None:
    """Replace hardcoded http://127.0.0.1:8000/wiki/ and en.wikipedia.org/wiki/ links with relative /wiki/ links."""
    import re
    # Fix 127.0.0.1:8000 links
    rows = db._fetchall(conn, "SELECT id, content FROM articles WHERE content LIKE '%127.0.0.1:8000%'")
    for row in rows:
        new_content = re.sub(r'https?://127\.0\.0\.1:8000/wiki/', '/wiki/', row["content"])
        if new_content != row["content"]:
            p = db._param_style()
            db._execute(conn, f"UPDATE articles SET content = {p} WHERE id = {p}", (new_content, row["id"]))
    # Fix en.wikipedia.org/wiki/ links in See also sections
    rows2 = db._fetchall(conn, "SELECT id, content FROM articles WHERE content LIKE '%en.wikipedia.org/wiki/%'")
    for row in rows2:
        new_content = re.sub(
            r'href="https?://en\.wikipedia\.org/wiki/([^"]+)"',
            r'href="/wiki/\1"',
            row["content"]
        )
        if new_content != row["content"]:
            p = db._param_style()
            db._execute(conn, f"UPDATE articles SET content = {p} WHERE id = {p}", (new_content, row["id"]))
    # Also fix revision history
    for table in ("revisions",):
        for col in ("content",):
            rev_rows = db._fetchall(conn, f"SELECT id, {col} FROM {table} WHERE {col} LIKE '%127.0.0.1:8000%' OR {col} LIKE '%en.wikipedia.org/wiki/%'")
            for row in rev_rows:
                new_content = row[col]
                new_content = re.sub(r'https?://127\.0\.0\.1:8000/wiki/', '/wiki/', new_content)
                new_content = re.sub(r'href="https?://en\.wikipedia\.org/wiki/([^"]+)"', r'href="/wiki/\1"', new_content)
                if new_content != row[col]:
                    p = db._param_style()
                    db._execute(conn, f"UPDATE {table} SET {col} = {p} WHERE id = {p}", (new_content, row["id"]))


def _migration_019_fix_wikipedia_links(conn) -> None:
    """Replace remaining en.wikipedia.org/wiki/ links with relative /wiki/ links.

    Migration 18 ran before the Wikipedia link fix was added, so this catches
    any articles that still have hardcoded Wikipedia URLs in their See also sections.
    """
    import re
    p = db._param_style()
    for table in ("articles", "revisions"):
        col = "content"
        rows = db._fetchall(conn, f"SELECT id, {col} FROM {table} WHERE {col} LIKE '%en.wikipedia.org/wiki/%'")
        for row in rows:
            new_content = re.sub(
                r'href="https?://en\.wikipedia\.org/wiki/([^"]+)"',
                r'href="/wiki/\1"',
                row[col]
            )
            if new_content != row[col]:
                db._execute(conn, f"UPDATE {table} SET {col} = {p} WHERE id = {p}", (new_content, row["id"]))


def _migration_020_topics_table(conn) -> None:
    """Create topics table for DB-backed topic management."""
    if db._table_exists(conn, "topics"):
        return
    sid = db._serial_id()
    bool_t = db._bool_type()
    default_val = "FALSE" if config.is_postgres() else "0"
    db._execute(
        conn,
        f"""CREATE TABLE topics (
            id {sid},
            title TEXT NOT NULL,
            slug TEXT NOT NULL,
            category TEXT NOT NULL,
            is_written {bool_t} NOT NULL DEFAULT {default_val},
            created_at TEXT NOT NULL
        )""",
    )
    db._execute(conn, "CREATE UNIQUE INDEX IF NOT EXISTS idx_topics_slug_category ON topics(slug, category)")
    db._execute(conn, "CREATE INDEX IF NOT EXISTS idx_topics_unwritten ON topics(category, is_written)")


MIGRATIONS: list[Migration] = [
    Migration(1, "initial_baseline", _migration_001_initial),
    Migration(2, "article_ownership_columns", _migration_002_article_ownership),
    Migration(3, "external_agents_last_seen", _migration_003_external_agents_last_seen),
    Migration(4, "external_agents_overview_link", _migration_004_external_agents_overview),
    Migration(5, "external_agents_webhook", _migration_005_external_agents_webhook),
    Migration(6, "backfill_agent_overviews", _migration_006_backfill_agent_overviews),
    Migration(7, "agent_presence_status", _migration_007_agent_presence_status),
    # 8 = pending_topics (legacy, already on prod)
    Migration(9, "users", _migration_009_users),
    Migration(10, "user_avatar_url", _migration_010_user_avatar_url),
    Migration(11, "user_email_password", _migration_011_user_email_password),
    Migration(12, "external_agents_user_id", _migration_012_external_agents_user_id),
    Migration(13, "user_locale", _migration_013_user_locale),
    Migration(14, "builtin_agents", _migration_014_builtin_agents),
    Migration(15, "user_server_invoke_usage", _migration_015_user_server_invoke_usage),
    Migration(16, "articles_tool_spec", _migration_016_articles_tool_spec),
    Migration(17, "pending_topics", _migration_017_pending_topics),
    Migration(18, "fix_hardcoded_urls", _migration_018_fix_hardcoded_urls),
    Migration(19, "fix_wikipedia_links", _migration_019_fix_wikipedia_links),
    Migration(20, "topics_table", _migration_020_topics_table),
]

CURRENT_VERSION = MIGRATIONS[-1].version

MIGRATION_NAMES = {m.version: m.name for m in MIGRATIONS}
