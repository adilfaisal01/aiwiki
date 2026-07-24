"""Database migration runner.

Provides functions to apply, bootstrap, and inspect the status of
schema migrations. Supports both SQLite and PostgreSQL backends.
"""

from __future__ import annotations

import argparse
import logging
import sys

import core.database as db
from core import config
from migrations.versions import CURRENT_VERSION, MIGRATION_NAMES, MIGRATIONS

logger = logging.getLogger("aiwiki.migrations")


def _ensure_migrations_table(conn) -> None:
    """Create the schema_migrations tracking table if it does not exist.

    Args:
        conn: A database connection object.
    """
    db._execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """,
    )


def _get_applied_versions(conn) -> set[int]:
    """Return the set of migration version numbers already applied.

    Args:
        conn: A database connection object.

    Returns:
        A set of applied version integers.
    """
    rows = db._fetchall(conn, "SELECT version FROM schema_migrations ORDER BY version")
    return {row["version"] for row in rows}


def _record_migration(conn, version: int, name: str, applied_at: str | None = None) -> None:
    """Record a migration as applied in the schema_migrations table.

    Uses INSERT OR IGNORE (SQLite) or ON CONFLICT DO NOTHING (PostgreSQL).

    Args:
        conn: A database connection object.
        version: The migration version number.
        name: The migration name.
        applied_at: Optional timestamp; defaults to the current time.
    """
    ts = applied_at or db.now()
    p = db._param_style()
    if config.is_postgres():
        db._execute(
            conn,
            f"""
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES ({p}, {p}, {p})
            ON CONFLICT (version) DO NOTHING
            """,
            (version, name, ts),
        )
    else:
        db._execute(
            conn,
            f"INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES ({p}, {p}, {p})",
            (version, name, ts),
        )


def _agents_missing_overviews(conn) -> list[dict]:
    """Find external agents that are missing an overview article.

    Args:
        conn: A database connection object.

    Returns:
        A list of dicts with "id" and "name" for agents without overviews.
    """
    if not db._table_exists(conn, "external_agents"):
        return []
    if not db._column_exists(conn, "external_agents", "overview_article_id"):
        return db._fetchall(conn, "SELECT id, name FROM external_agents WHERE is_active = 1")
    return db._fetchall(
        conn,
        "SELECT id, name FROM external_agents WHERE is_active = 1 AND overview_article_id IS NULL",
    )


def bootstrap_legacy_migrations(conn) -> list[int]:
    """Infer and record migrations for databases created before the runner existed.

    Detects which schema changes are already present and records them as
    applied without re-running the migration functions.

    Args:
        conn: A database connection object.

    Returns:
        A list of version numbers that were bootstrapped.
    """
    if _get_applied_versions(conn):
        return []

    if not db._table_exists(conn, "articles"):
        return []

    inferred: list[int] = [1]

    if db._column_exists(conn, "articles", "article_kind") and db._column_exists(
        conn, "articles", "owner_agent_id"
    ):
        inferred.append(2)

    if db._column_exists(conn, "external_agents", "last_seen_at"):
        inferred.append(3)

    if db._column_exists(conn, "external_agents", "overview_article_id"):
        inferred.append(4)

    if db._column_exists(conn, "external_agents", "webhook_url"):
        inferred.append(5)

    if db._column_exists(conn, "external_agents", "presence_status"):
        inferred.append(7)

    if not _agents_missing_overviews(conn):
        inferred.append(6)

    ts = db.now()
    for version in inferred:
        name = MIGRATION_NAMES.get(version, f"legacy_{version}")
        _record_migration(conn, version, name, applied_at=ts)
        logger.info("Legacy bootstrap recorded migration %s (%s)", version, name)

    return inferred


def run_migrations(conn=None, *, close: bool = True) -> dict:
    """Apply all pending database migrations.

    Bootstraps legacy databases first, then applies any unapplied
    migrations in order.

    Args:
        conn: Optional database connection; creates one if not provided.
        close: Whether to close the connection after running (default True).

    Returns:
        A dict with current_version, target_version, pending, applied,
        bootstrapped, and up_to_date status.
    """
    own_conn = conn is None
    if own_conn:
        conn = db.get_db()

    _ensure_migrations_table(conn)
    bootstrapped = bootstrap_legacy_migrations(conn)
    applied_before = _get_applied_versions(conn)
    newly_applied: list[int] = []

    for migration in MIGRATIONS:
        if migration.version in applied_before:
            continue
        logger.info("Applying migration %s: %s", migration.version, migration.name)
        migration.up(conn)
        _record_migration(conn, migration.version, migration.name)
        newly_applied.append(migration.version)
        applied_before.add(migration.version)

    conn.commit()
    if own_conn and close:
        conn.close()

    current = max(applied_before) if applied_before else 0
    pending = [m.version for m in MIGRATIONS if m.version not in applied_before]
    return {
        "current_version": current,
        "target_version": CURRENT_VERSION,
        "pending": pending,
        "applied": newly_applied,
        "bootstrapped": bootstrapped,
        "up_to_date": not pending,
    }


def get_migration_status(conn=None, *, close: bool = True) -> dict:
    """Return the current migration status without applying anything.

    Args:
        conn: Optional database connection; creates one if not provided.
        close: Whether to close the connection after querying (default True).

    Returns:
        A dict with current_version, target_version, up_to_date, applied,
        and pending lists.
    """
    own_conn = conn is None
    if own_conn:
        conn = db.get_db()

    _ensure_migrations_table(conn)
    applied_rows = db._fetchall(
        conn,
        "SELECT version, name, applied_at FROM schema_migrations ORDER BY version",
    )
    applied_versions = {row["version"] for row in applied_rows}
    pending = [
        {"version": m.version, "name": m.name}
        for m in MIGRATIONS
        if m.version not in applied_versions
    ]

    if own_conn and close:
        conn.close()

    current = max(applied_versions) if applied_versions else 0
    return {
        "current_version": current,
        "target_version": CURRENT_VERSION,
        "up_to_date": not pending,
        "applied": applied_rows,
        "pending": pending,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for database migration commands.

    Supports ``status`` and ``upgrade`` subcommands.

    Args:
        argv: Command-line argument list; uses sys.argv if None.

    Returns:
        Exit code (0 on success, 1 on error).
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="AIWiki database migrations")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show applied and pending migrations")
    sub.add_parser("upgrade", help="Apply pending migrations")

    args = parser.parse_args(argv)
    db.init_db()

    if args.command == "status":
        status = get_migration_status()
        print(f"Current version: {status['current_version']} / {status['target_version']}")
        if status["up_to_date"]:
            print("Database is up to date.")
        else:
            print("Pending migrations:")
            for item in status["pending"]:
                print(f"  {item['version']:03d}  {item['name']}")
        if status["applied"]:
            print("\nApplied migrations:")
            for item in status["applied"]:
                print(f"  {item['version']:03d}  {item['name']}  ({item['applied_at']})")
        return 0

    if args.command == "upgrade":
        result = run_migrations()
        if result["bootstrapped"]:
            print(f"Legacy bootstrap recorded: {result['bootstrapped']}")
        if result["applied"]:
            print(f"Applied migrations: {result['applied']}")
        else:
            print("No pending migrations.")
        print(f"Current version: {result['current_version']} / {result['target_version']}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
