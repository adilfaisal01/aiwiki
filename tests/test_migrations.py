import os
import tempfile
from pathlib import Path

import importlib
import pytest


def _restore_test_database():
  original = os.environ.get("AIWIKI_DATABASE_URL")
  pytest_db = Path(tempfile.gettempdir()) / "aiwiki_pytest.db"
  os.environ["AIWIKI_DATABASE_URL"] = f"sqlite:///{pytest_db}"

  import core.config as config
  import core.database as db
  import main

  importlib.reload(config)
  importlib.reload(db)
  main._db_initialized = False


def test_fresh_database_applies_all_migrations():
    db_path = Path(tempfile.gettempdir()) / f"aiwiki_migrate_fresh_{os.getpid()}.db"
    if db_path.exists():
        db_path.unlink()

    os.environ["AIWIKI_DATABASE_URL"] = f"sqlite:///{db_path}"

    try:
        import core.config as config
        import core.database as db
        import migrations.runner as runner

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(runner)

        db.init_db()
        status = runner.get_migration_status()
        assert status["up_to_date"] is True
        assert status["current_version"] == status["target_version"]
        conn = db.get_db()
        assert db._column_exists(conn, "articles", "article_kind")
        assert db._column_exists(conn, "articles", "tool_spec_json")
        assert db._column_exists(conn, "articles", "needs_review")
        assert db._column_exists(conn, "articles", "category")
        assert db._table_exists(conn, "pending_topics")
        assert db._column_exists(conn, "external_agents", "webhook_url")
        conn.close()
    finally:
        _restore_test_database()


def test_legacy_database_bootstrap_without_rerunning_alters():
    db_path = Path(tempfile.gettempdir()) / f"aiwiki_migrate_legacy_{os.getpid()}.db"
    if db_path.exists():
        db_path.unlink()

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL UNIQUE,
            slug TEXT NOT NULL UNIQUE,
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            article_kind TEXT NOT NULL DEFAULT 'encyclopedia',
            owner_agent_id INTEGER
        );
        CREATE TABLE external_agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            api_key_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_seen_at TEXT,
            overview_article_id INTEGER,
            webhook_url TEXT
        );
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version (version) VALUES (1);
        INSERT INTO external_agents (name, api_key_hash, created_at, is_active, last_seen_at)
        VALUES ('LegacyBot', 'abc', '2020-01-01T00:00:00+00:00', 1, '2020-01-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    os.environ["AIWIKI_DATABASE_URL"] = f"sqlite:///{db_path}"

    try:
        import core.config as config
        import core.database as db
        import migrations.runner as runner

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(runner)

        db.init_db()

        status = runner.get_migration_status()
        assert status["up_to_date"] is True

        conn = db.get_db()
        agent = db._fetchone(conn, "SELECT overview_article_id FROM external_agents WHERE name = 'LegacyBot'")
        conn.close()
        assert agent["overview_article_id"] is not None
    finally:
        _restore_test_database()


def test_health_includes_migration_status(client):
    response = client.get("/health")
    assert response.status_code == 200
    migrations = response.json()["migrations"]
    assert migrations["up_to_date"] is True
    assert "current_version" in migrations
    assert "target_version" in migrations
