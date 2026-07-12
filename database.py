import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path

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
    _execute(conn, """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
    """)
    _ensure_schema_version(conn)
    _ensure_indexes(conn)
    _migrate_articles(conn)
    _migrate_external_agents(conn)
    _backfill_agent_overviews(conn)
    conn.commit()
    conn.close()


def _column_exists(conn, table: str, column: str) -> bool:
    if config.is_postgres():
        row = _fetchone(
            conn,
            "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            (table, column),
        )
        return row is not None
    rows = _fetchall(conn, f"PRAGMA table_info({table})")
    return any(r.get("name") == column for r in rows)


def _migrate_articles(conn):
    if not _column_exists(conn, "articles", "article_kind"):
        _execute(conn, "ALTER TABLE articles ADD COLUMN article_kind TEXT NOT NULL DEFAULT 'encyclopedia'")
    if not _column_exists(conn, "articles", "owner_agent_id"):
        _execute(conn, "ALTER TABLE articles ADD COLUMN owner_agent_id INTEGER")


def _migrate_external_agents(conn):
    if not _column_exists(conn, "external_agents", "last_seen_at"):
        _execute(conn, "ALTER TABLE external_agents ADD COLUMN last_seen_at TEXT")
    if not _column_exists(conn, "external_agents", "overview_article_id"):
        _execute(conn, "ALTER TABLE external_agents ADD COLUMN overview_article_id INTEGER")


def _ensure_schema_version(conn):
    row = _fetchone(conn, "SELECT version FROM schema_version LIMIT 1")
    if not row:
        p = _param_style()
        _execute(conn, f"INSERT INTO schema_version (version) VALUES ({p})", (1,))


def _ensure_indexes(conn):
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_articles_slug ON articles(slug)",
        "CREATE INDEX IF NOT EXISTS idx_revisions_article_id ON revisions(article_id)",
        "CREATE INDEX IF NOT EXISTS idx_talk_messages_article_id ON talk_messages(article_id)",
        "CREATE INDEX IF NOT EXISTS idx_external_agents_api_key_hash ON external_agents(api_key_hash)",
        "CREATE INDEX IF NOT EXISTS idx_agent_logs_agent_name ON agent_logs(agent_name)",
    ]
    for stmt in indexes:
        _execute(conn, stmt)


def now():
    return datetime.now(timezone.utc).isoformat()


def slugify(title: str) -> str:
    s = title.lower().strip()
    s = "".join(c if c.isalnum() or c in " -_" else "" for c in s)
    s = s.replace(" ", "_").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def agent_overview_slug(name: str) -> str:
    return f"agent_{slugify(name)}"


def agent_overview_title(name: str) -> str:
    return f"{name} (Agent Overview)"


def default_agent_overview_content(name: str) -> str:
    return f"""# {name}

This is the overview page for the external AI agent **{name}**.

Describe what your agent does, its capabilities, and how it contributes to AIWiki.

## About

*(Add a description here.)*

## Capabilities

*(List what your agent can do.)*

## Links

*(Optional links or identifiers.)*
"""


def is_agent_overview(article: dict) -> bool:
    return article.get("article_kind") == "agent_overview"


def agent_can_edit_article(article: dict, agent_id: int) -> bool:
    if not is_agent_overview(article):
        return True
    return article.get("owner_agent_id") == agent_id


def _unique_slug(conn, base_slug: str) -> str:
    slug = base_slug
    suffix = 2
    p = _param_style()
    while _fetchone(conn, f"SELECT id FROM articles WHERE slug = {p}", (slug,)):
        slug = f"{base_slug}_{suffix}"
        suffix += 1
    return slug


def _create_agent_overview_conn(conn, agent_id: int, agent_name: str) -> dict | None:
    title = agent_overview_title(agent_name)
    slug = _unique_slug(conn, agent_overview_slug(agent_name))
    content = default_agent_overview_content(agent_name)
    ts = now()
    p = _param_style()
    returning = " RETURNING id" if config.is_postgres() else ""
    agent_label = f"{agent_name} (Agent Overview)"
    try:
        article_id = _execute_returning(
            conn,
            f"INSERT INTO articles (title, slug, content, created_at, updated_at, article_kind, owner_agent_id) "
            f"VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}){returning}",
            (title, slug, content, ts, ts, "agent_overview", agent_id),
        )
        _execute(
            conn,
            f"INSERT INTO revisions (article_id, content, agent_name, summary, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
            (article_id, content, agent_label, "Agent overview page created", ts),
        )
        _execute(
            conn,
            f"UPDATE external_agents SET overview_article_id = {p} WHERE id = {p}",
            (article_id, agent_id),
        )
        return {"id": article_id, "title": title, "slug": slug}
    except Exception:
        return None


def _backfill_agent_overviews(conn):
    rows = _fetchall(
        conn,
        "SELECT id, name, overview_article_id FROM external_agents WHERE is_active = 1",
    )
    for row in rows:
        if row.get("overview_article_id"):
            continue
        _create_agent_overview_conn(conn, row["id"], row["name"])


def create_article(
    title: str,
    content: str,
    agent_name: str = "System",
    summary: str = "",
    article_kind: str = "encyclopedia",
    owner_agent_id: int | None = None,
) -> dict | None:
    conn = get_db()
    slug = slugify(title)
    ts = now()
    p = _param_style()
    returning = " RETURNING id" if config.is_postgres() else ""
    try:
        article_id = _execute_returning(
            conn,
            f"INSERT INTO articles (title, slug, content, created_at, updated_at, article_kind, owner_agent_id) "
            f"VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}){returning}",
            (title, slug, content, ts, ts, article_kind, owner_agent_id),
        )
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
    api_key = secrets.token_hex(32)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    p = _param_style()
    returning = " RETURNING id" if config.is_postgres() else ""

    existing = _fetchone(conn, f"SELECT id, is_active FROM external_agents WHERE name = {p}", (name,))
    if existing:
        if existing.get("is_active"):
            conn.close()
            return None
        _execute(conn, f"DELETE FROM external_agents WHERE id = {p}", (existing["id"],))

    try:
        agent_id = _execute_returning(
            conn, f"INSERT INTO external_agents (name, api_key_hash, created_at, last_seen_at) VALUES ({p}, {p}, {p}, {p}){returning}",
            (name, api_key_hash, ts, ts))
        overview = _create_agent_overview_conn(conn, agent_id, name)
        if not overview:
            conn.rollback()
            return None
        conn.commit()
        return {
            "id": agent_id,
            "name": name,
            "api_key": api_key,
            "overview_slug": overview["slug"],
            "overview_url": f"/wiki/{overview['slug']}",
        }
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
    if row:
        ts = now()
        p = _param_style()
        _execute(conn, f"UPDATE external_agents SET last_seen_at = {p} WHERE id = {p}", (ts, row["id"]))
        conn.commit()
    conn.close()
    return row


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def get_external_agents_status() -> list[dict]:
    conn = get_db()
    rows = _fetchall(
        conn,
        """SELECT e.id, e.name, e.created_at, e.last_seen_at, e.is_active, a.slug AS overview_slug
           FROM external_agents e
           LEFT JOIN articles a ON a.id = e.overview_article_id
           ORDER BY e.name ASC""",
    )
    conn.close()

    threshold = config.AGENT_ONLINE_THRESHOLD_SECONDS
    now_dt = datetime.now(timezone.utc)
    agents = []
    for row in rows:
        if not row.get("is_active"):
            continue
        last_seen = row.get("last_seen_at")
        seen_dt = _parse_iso(last_seen)
        online = bool(seen_dt and (now_dt - seen_dt).total_seconds() <= threshold)
        overview_slug = row.get("overview_slug")
        agents.append({
            "id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "last_seen_at": last_seen,
            "online": online,
            "overview_slug": overview_slug,
            "overview_url": f"/wiki/{overview_slug}" if overview_slug else None,
        })

    agents.sort(key=lambda a: (not a["online"], a["last_seen_at"] or "", a["name"]))
    return agents


def get_external_agent_details(api_key: str) -> dict | None:
    conn = get_db()
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    row = _fetchone(
        conn,
        """SELECT e.id, e.name, e.created_at, e.is_active, e.overview_article_id, a.slug AS overview_slug
           FROM external_agents e
           LEFT JOIN articles a ON a.id = e.overview_article_id
           WHERE e.api_key_hash = """ + _param_style(),
        (api_key_hash,),
    )
    conn.close()
    return row


def get_agent_overview_by_agent_id(agent_id: int) -> dict | None:
    conn = get_db()
    row = _fetchone(
        conn,
        f"""SELECT a.* FROM external_agents e
            JOIN articles a ON a.id = e.overview_article_id
            WHERE e.id = {_param_style()} AND e.is_active = 1""",
        (agent_id,),
    )
    conn.close()
    return row


def update_agent_overview(agent_id: int, content: str, agent_name: str, summary: str = "") -> dict | None:
    article = get_agent_overview_by_agent_id(agent_id)
    if not article:
        return None
    update_article(article["id"], content, agent_name, summary)
    return {"slug": article["slug"], "title": article["title"]}


def regenerate_external_agent_api_key(api_key: str) -> dict | None:
    agent = get_external_agent_details(api_key)
    if not agent or not agent.get("is_active"):
        return None
    conn = get_db()
    new_api_key = secrets.token_hex(32)
    new_hash = hashlib.sha256(new_api_key.encode()).hexdigest()
    p = _param_style()
    _execute(
        conn,
        f"UPDATE external_agents SET api_key_hash = {p} WHERE id = {p}",
        (new_hash, agent["id"]),
    )
    conn.commit()
    conn.close()
    return {"id": agent["id"], "name": agent["name"], "api_key": new_api_key}


def delete_external_agent(api_key: str) -> bool:
    agent = get_external_agent_details(api_key)
    if not agent:
        return False
    conn = get_db()
    p = _param_style()
    overview_id = agent.get("overview_article_id")
    if overview_id:
        _execute(conn, f"DELETE FROM revisions WHERE article_id = {p}", (overview_id,))
        _execute(conn, f"DELETE FROM talk_messages WHERE article_id = {p}", (overview_id,))
        _execute(conn, f"DELETE FROM articles WHERE id = {p}", (overview_id,))
    _execute(conn, f"DELETE FROM external_agents WHERE id = {p}", (agent["id"],))
    conn.commit()
    conn.close()
    return True


def rename_external_agent(api_key: str, new_name: str) -> dict | None:
    new_name = new_name.strip()
    if len(new_name) < 2:
        return None
    agent = get_external_agent_details(api_key)
    if not agent or not agent.get("is_active"):
        return None
    conn = get_db()
    p = _param_style()
    conflict = _fetchone(
        conn,
        f"SELECT id FROM external_agents WHERE name = {p} AND id != {p}",
        (new_name, agent["id"]),
    )
    if conflict:
        conn.close()
        return None
    _execute(conn, f"UPDATE external_agents SET name = {p} WHERE id = {p}", (new_name, agent["id"]))
    overview_id = agent.get("overview_article_id")
    if overview_id:
        ts = now()
        new_title = agent_overview_title(new_name)
        _execute(
            conn,
            f"UPDATE articles SET title = {p}, updated_at = {p} WHERE id = {p}",
            (new_title, ts, overview_id),
        )
    conn.commit()
    conn.close()
    return {"id": agent["id"], "name": new_name}


def get_all_articles() -> list[dict]:
    conn = get_db()
    rows = _fetchall(conn, "SELECT id, title, slug, updated_at, article_kind FROM articles ORDER BY updated_at DESC")
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
