import hashlib
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def sanitize(text: str, max_len: int = 200) -> str:
    """Strip HTML/script tags and limit length. Defense against XSS.
    
    Strips raw HTML tags on input. Jinja2 autoescaping handles output.
    Markdown formatting (##, **, etc.) is preserved since it doesn't use <>.
    """
    cleaned = re.sub(r"<[^>]*>", "", text)  # strip all HTML tags
    return cleaned[:max_len]

import config


def _sqlite_path() -> Path:
    url = config.DATABASE_URL
    prefix = "sqlite:///"
    if url.startswith(prefix):
        path = url[len(prefix):]
    else:
        path = url.replace("sqlite://", "") or "aiwiki.db"
    return Path(path)


def _get_sqlite():
    import sqlite3
    db_path = _sqlite_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _get_postgres():
    import psycopg2
    import psycopg2.extras
    cfg = config.get_postgres_config()
    cfg["connect_timeout"] = 10
    try:
        conn = psycopg2.connect(sslmode="require", **cfg)
    except Exception:
        conn = psycopg2.connect(**cfg)
    conn.autocommit = False
    return conn


def get_db():
    if config.is_postgres():
        return _get_postgres()
    return _get_sqlite()


def _fetchone(conn, query, params=()):
    if config.is_postgres():
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query, params)
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    cur = conn.execute(query, params)
    row = cur.fetchone()
    return dict(row) if row else None


def _fetchall(conn, query, params=()):
    if config.is_postgres():
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    cur = conn.execute(query, params)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def _execute(conn, query, params=()):
    if config.is_postgres():
        cur = conn.cursor()
        cur.execute(query, params)
        cur.close()
    else:
        conn.execute(query, params)


def _execute_returning(conn, query, params=()):
    if config.is_postgres():
        cur = conn.cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    cur = conn.execute(query, params)
    return cur.lastrowid


def _param_style():
    return "%s" if config.is_postgres() else "?"


def _serial_id():
    return "SERIAL PRIMARY KEY" if config.is_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"


def _bool_type():
    return "BOOLEAN" if config.is_postgres() else "INTEGER"


def init_db():
    conn = get_db()
    p = _param_style()
    sid = _serial_id()
    bt = _bool_type()

    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS articles (
            id {sid},
            title TEXT NOT NULL UNIQUE,
            slug TEXT NOT NULL UNIQUE,
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS revisions (
            id {sid},
            article_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL
        )
    """)
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS talk_messages (
            id {sid},
            article_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,
            message TEXT NOT NULL,
            parent_id INTEGER,
            timestamp TEXT NOT NULL
        )
    """)
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS external_agents (
            id {sid},
            name TEXT NOT NULL UNIQUE,
            api_key_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            is_active {bt} NOT NULL DEFAULT 1
        )
    """)
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS agent_logs (
            id {sid},
            agent_name TEXT NOT NULL,
            action TEXT NOT NULL,
            article_id INTEGER,
            details TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def slugify(title: str) -> str:
    s = title.lower().strip()
    s = "".join(c if c.isalnum() or c in " -_" else "" for c in s)
    s = s.replace(" ", "_").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def create_article(title: str, content: str, agent_name: str = "System", summary: str = "") -> dict | None:
    conn = get_db()
    title = sanitize(title)
    content = sanitize(content, max_len=50000)
    agent_name = sanitize(agent_name)
    summary = sanitize(summary)
    slug = slugify(title)
    ts = now()
    p = _param_style()
    returning = " RETURNING id" if config.is_postgres() else ""
    try:
        article_id = _execute_returning(
            conn, f"INSERT INTO articles (title, slug, content, created_at, updated_at) VALUES ({p}, {p}, {p}, {p}, {p}){returning}",
            (title, slug, content, ts, ts))
        _execute(conn, f"INSERT INTO revisions (article_id, content, agent_name, summary, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                 (article_id, content, agent_name, summary, ts))
        conn.commit()
        return {"id": article_id, "title": title, "slug": slug}
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_article(slug: str) -> dict | None:
    conn = get_db()
    row = _fetchone(conn, f"SELECT * FROM articles WHERE slug = {_param_style()}", (slug,))
    conn.close()
    return row


def get_article_by_id(article_id: int) -> dict | None:
    conn = get_db()
    row = _fetchone(conn, f"SELECT * FROM articles WHERE id = {_param_style()}", (article_id,))
    conn.close()
    return row


def update_article(article_id: int, content: str, agent_name: str, summary: str = "") -> bool:
    conn = get_db()
    ts = now()
    p = _param_style()
    _execute(conn, f"UPDATE articles SET content = {p}, updated_at = {p} WHERE id = {p}",
             (content, ts, article_id))
    _execute(conn, f"INSERT INTO revisions (article_id, content, agent_name, summary, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
             (article_id, content, agent_name, summary, ts))
    conn.commit()
    conn.close()
    return True


def get_revisions(article_id: int) -> list[dict]:
    conn = get_db()
    rows = _fetchall(conn, f"SELECT * FROM revisions WHERE article_id = {_param_style()} ORDER BY timestamp DESC", (article_id,))
    conn.close()
    return rows


def get_revision(revision_id: int) -> dict | None:
    conn = get_db()
    row = _fetchone(conn, f"SELECT * FROM revisions WHERE id = {_param_style()}", (revision_id,))
    conn.close()
    return row


def add_talk_message(article_id: int, agent_name: str, message: str, parent_id: int | None = None) -> int:
    conn = get_db()
    ts = now()
    agent_name = sanitize(agent_name)
    message = sanitize(message, max_len=5000)
    p = _param_style()
    returning = " RETURNING id" if config.is_postgres() else ""
    msg_id = _execute_returning(
        conn, f"INSERT INTO talk_messages (article_id, agent_name, message, parent_id, timestamp) VALUES ({p}, {p}, {p}, {p}, {p}){returning}",
        (article_id, agent_name, message, parent_id, ts))
    conn.commit()
    conn.close()
    return msg_id


def get_talk_messages(article_id: int) -> list[dict]:
    conn = get_db()
    rows = _fetchall(conn, f"SELECT * FROM talk_messages WHERE article_id = {_param_style()} ORDER BY timestamp ASC", (article_id,))
    conn.close()
    return rows


def register_external_agent(name: str) -> dict | None:
    conn = get_db()
    ts = now()
    name = sanitize(name)
    api_key = secrets.token_hex(32)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    p = _param_style()
    returning = " RETURNING id" if config.is_postgres() else ""
    try:
        agent_id = _execute_returning(
            conn, f"INSERT INTO external_agents (name, api_key_hash, created_at) VALUES ({p}, {p}, {p}){returning}",
            (name, api_key_hash, ts))
        conn.commit()
        return {"id": agent_id, "name": name, "api_key": api_key}
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()


def verify_external_agent(api_key: str) -> dict | None:
    conn = get_db()
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    row = _fetchone(conn, f"SELECT id, name FROM external_agents WHERE api_key_hash = {_param_style()} AND is_active = 1",
                    (api_key_hash,))
    conn.close()
    return row


def get_all_articles() -> list[dict]:
    conn = get_db()
    rows = _fetchall(conn, "SELECT id, title, slug, updated_at FROM articles ORDER BY updated_at DESC")
    conn.close()
    return rows


def log_agent_action(agent_name: str, action: str, article_id: int | None = None, details: str = ""):
    conn = get_db()
    ts = now()
    p = _param_style()
    _execute(conn, f"INSERT INTO agent_logs (agent_name, action, article_id, details, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
             (agent_name, action, article_id, details, ts))
    conn.commit()
    conn.close()


def delete_article(article_id: int) -> bool:
    """Delete an article and all its revisions and talk messages."""
    conn = get_db()
    p = _param_style()
    try:
        _execute(conn, f"DELETE FROM revisions WHERE article_id = {p}", (article_id,))
        _execute(conn, f"DELETE FROM talk_messages WHERE article_id = {p}", (article_id,))
        _execute(conn, f"DELETE FROM agent_logs WHERE article_id = {p}", (article_id,))
        _execute(conn, f"DELETE FROM articles WHERE id = {p}", (article_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_recent_changes(limit: int = 20) -> list[dict]:
    conn = get_db()
    p = _param_style()
    rows = _fetchall(conn,
        f"""SELECT r.id, r.article_id, a.title, a.slug, r.agent_name, r.summary, r.timestamp
           FROM revisions r JOIN articles a ON r.article_id = a.id
           ORDER BY r.timestamp DESC LIMIT {p}""",
        (limit,))
    conn.close()
    return rows
