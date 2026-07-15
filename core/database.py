import hashlib
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def sanitize(text: str, max_len: int = 200) -> str:
    """Strip HTML/script tags and limit length. Defense against XSS.
    
    Strips raw HTML tags on input. Jinja2 autoescaping handles output.
    Markdown formatting (##, **, etc.) is preserved since it doesn't use <>.
    """
    cleaned = re.sub(r"<[^>]*>", "", text)  # strip all HTML tags
    return cleaned[:max_len]


def prepare_article_content(content: str, max_len: int = 500_000) -> str:
    """Store encyclopedia article bodies; preserve HTML for blueprint/mirror articles."""
    content = content.replace("\x00", "")
    if content.lstrip().startswith("<"):
        return content[:max_len]
    return sanitize(content, max_len=max_len)

from core import config


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
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    # Only set WAL mode if not already set (avoids exclusive lock on every connect)
    cur = conn.execute("PRAGMA journal_mode")
    if cur.fetchone()[0] != "wal":
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()  # Clear implicit transaction from PRAGMAs
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
        import time
        for attempt in range(5):
            try:
                conn.execute(query, params)
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < 4:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise


def _execute_returning(conn, query, params=()):
    if config.is_postgres():
        cur = conn.cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    import time
    for attempt in range(5):
        try:
            cur = conn.execute(query, params)
            return cur.lastrowid
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < 4:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise


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
    # Ensure needs_review column exists (safe for SQLite ALTER TABLE)
    if not _column_exists(conn, "articles", "needs_review"):
        _execute(conn, "ALTER TABLE articles ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0")
    # Ensure category column exists (safe for SQLite ALTER TABLE)
    if not _column_exists(conn, "articles", "category"):
        _execute(conn, "ALTER TABLE articles ADD COLUMN category TEXT NOT NULL DEFAULT 'science'")
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
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS builtin_agents (
            id {sid},
            name TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_seen_at TEXT,
            last_action TEXT,
            last_action_at TEXT,
            overview_article_id INTEGER
        )
    """)
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS pending_topics (
            id {sid},
            topic TEXT NOT NULL UNIQUE,
            source_article_id INTEGER,
            category TEXT NOT NULL DEFAULT 'science',
            queued_at TEXT NOT NULL,
            picked_at TEXT
        )
    """)
    _execute(conn, """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
    """)
    _ensure_indexes(conn)
    from migrations.runner import run_migrations

    run_migrations(conn, close=False)
    conn.close()


def _table_exists(conn, table: str) -> bool:
    if config.is_postgres():
        row = _fetchone(
            conn,
            "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
            (table,),
        )
        return row is not None
    row = _fetchone(conn, "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))
    return row is not None


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


def default_agent_overview_content(name: str, role: str = "external", *, builtin: bool | None = None) -> str:
    is_builtin = builtin if builtin is not None else role == "builtin"
    if is_builtin:
        from core.builtin_agents import default_builtin_overview_content

        return default_builtin_overview_content(name)
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


def is_aitool(article: dict) -> bool:
    return article.get("article_kind") == "aitool"


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


def _create_agent_overview_conn(
    conn,
    agent_id: int,
    agent_name: str,
    role: str = "external",
    *,
    builtin: bool = False,
) -> dict | None:
    title = agent_overview_title(agent_name)
    slug = _unique_slug(conn, agent_overview_slug(agent_name))
    overview_role = "builtin" if builtin else role
    content = default_agent_overview_content(agent_name, overview_role)
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
        if builtin or role == "builtin":
            _execute(
                conn,
                f"UPDATE builtin_agents SET overview_article_id = {p} WHERE id = {p}",
                (article_id, agent_id),
            )
        else:
            _execute(
                conn,
                f"UPDATE external_agents SET overview_article_id = {p} WHERE id = {p}",
                (article_id, agent_id),
            )
        return {"id": article_id, "title": title, "slug": slug}
    except Exception:
        return None


def seed_builtin_agents(conn) -> int:
    from core.builtin_agents import BUILTIN_AGENTS

    p = _param_style()
    ts = now()
    seeded = 0
    for agent in BUILTIN_AGENTS:
        existing = _fetchone(conn, f"SELECT id, overview_article_id FROM builtin_agents WHERE name = {p}", (agent["name"],))
        if existing:
            if not existing.get("overview_article_id"):
                if _create_agent_overview_conn(conn, existing["id"], agent["name"], builtin=True):
                    seeded += 1
            continue
        agent_id = _execute_returning(
            conn,
            f"INSERT INTO builtin_agents (name, role, created_at, last_seen_at) "
            f"VALUES ({p}, {p}, {p}, {p})"
            + (" RETURNING id" if config.is_postgres() else ""),
            (agent["name"], agent["role"], ts, ts),
        )
        if agent_id and _create_agent_overview_conn(conn, agent_id, agent["name"], builtin=True):
            seeded += 1
    return seeded


def update_agent_activity(agent_name: str, action: str = "") -> None:
    conn = get_db()
    ts = now()
    p = _param_style()
    builtin = _fetchone(conn, f"SELECT id FROM builtin_agents WHERE name = {p}", (agent_name,))
    if builtin:
        _execute(
            conn,
            f"UPDATE builtin_agents SET last_seen_at = {p}, last_action = {p}, last_action_at = {p} WHERE id = {p}",
            (ts, action, ts, builtin["id"]),
        )
    else:
        _execute(
            conn,
            f"UPDATE external_agents SET last_seen_at = {p}, last_action = {p}, last_action_at = {p} WHERE name = {p} AND is_active = 1",
            (ts, action, ts, agent_name),
        )
    conn.commit()
    conn.close()


def backfill_agent_overviews(conn) -> int:
    rows = _fetchall(
        conn,
        "SELECT id, name, overview_article_id FROM external_agents WHERE is_active = 1",
    )
    created = 0
    for row in rows:
        if row.get("overview_article_id"):
            continue
        if _create_agent_overview_conn(conn, row["id"], row["name"]):
            created += 1
    return created


def create_article(
    title: str,
    content: str,
    agent_name: str = "System",
    summary: str = "",
    article_kind: str = "encyclopedia",
    owner_agent_id: int | None = None,
    needs_review: bool = False,
    category: str = "science",
    tool_spec_json: str | None = None,
) -> dict | None:
    conn = get_db()
    title = sanitize(title)
    content = prepare_article_content(content)
    agent_name = sanitize(agent_name)
    summary = sanitize(summary)
    slug = slugify(title)
    ts = now()
    p = _param_style()
    returning = " RETURNING id" if config.is_postgres() else ""
    # Ensure needs_review column exists (safe for SQLite ALTER TABLE)
    if not _column_exists(conn, "articles", "needs_review"):
        _execute(conn, "ALTER TABLE articles ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0")
    # Ensure category column exists
    if not _column_exists(conn, "articles", "category"):
        _execute(conn, "ALTER TABLE articles ADD COLUMN category TEXT NOT NULL DEFAULT 'science'")
    if not _column_exists(conn, "articles", "tool_spec_json"):
        _execute(conn, "ALTER TABLE articles ADD COLUMN tool_spec_json TEXT")
    try:
        article_id = _execute_returning(
            conn,
            f"INSERT INTO articles (title, slug, content, created_at, updated_at, article_kind, owner_agent_id, needs_review, category, tool_spec_json) "
            f"VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}){returning}",
            (title, slug, content, ts, ts, article_kind, owner_agent_id, 1 if needs_review else 0, category, tool_spec_json),
        )
        _execute(conn, f"INSERT INTO revisions (article_id, content, agent_name, summary, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                 (article_id, content, agent_name, summary, ts))
        conn.commit()
        return {"id": article_id, "title": title, "slug": slug, "tool_spec_json": tool_spec_json}
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


def update_article(
    article_id: int,
    content: str,
    agent_name: str,
    summary: str = "",
    *,
    tool_spec_json: str | None = None,
    update_tool_spec: bool = False,
) -> bool:
    conn = get_db()
    ts = now()
    p = _param_style()
    if update_tool_spec:
        _execute(
            conn,
            f"UPDATE articles SET content = {p}, updated_at = {p}, tool_spec_json = {p} WHERE id = {p}",
            (content, ts, tool_spec_json, article_id),
        )
    else:
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


def add_talk_message(article_id: int, agent_name: str, message: str, parent_id: int | None = None, conn=None) -> int:
    own_conn = conn is None
    if own_conn:
        conn = get_db()
    ts = now()
    agent_name = sanitize(agent_name)
    message = sanitize(message, max_len=5000)
    p = _param_style()
    returning = " RETURNING id" if config.is_postgres() else ""
    msg_id = _execute_returning(
        conn, f"INSERT INTO talk_messages (article_id, agent_name, message, parent_id, timestamp) VALUES ({p}, {p}, {p}, {p}, {p}){returning}",
        (article_id, agent_name, message, parent_id, ts))
    if own_conn:
        conn.commit()
        conn.close()
    return msg_id


def get_talk_messages(article_id: int) -> list[dict]:
    conn = get_db()
    rows = _fetchall(conn, f"SELECT * FROM talk_messages WHERE article_id = {_param_style()} ORDER BY timestamp ASC", (article_id,))
    conn.close()
    return rows


def register_external_agent(name: str, user_id: str | None = None) -> dict | None:
    conn = get_db()
    ts = now()
    name = sanitize(name)
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
            conn,
            f"INSERT INTO external_agents (name, api_key_hash, created_at, last_seen_at, user_id) "
            f"VALUES ({p}, {p}, {p}, {p}, {p}){returning}",
            (name, api_key_hash, ts, ts, user_id),
        )
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
    row = _fetchone(
        conn,
        f"SELECT id, name, user_id FROM external_agents WHERE api_key_hash = {_param_style()} AND is_active = 1",
        (api_key_hash,),
    )
    if row:
        ts = now()
        p = _param_style()
        _execute(conn, f"UPDATE external_agents SET last_seen_at = {p} WHERE id = {p}", (ts, row["id"]))
        conn.commit()
    conn.close()
    return row


def current_usage_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def record_server_tool_invoke(user_id: str) -> int:
    period = current_usage_period()
    conn = get_db()
    p = _param_style()
    _execute(
        conn,
        f"""
        INSERT INTO user_server_invoke_usage (user_id, period, invoke_count)
        VALUES ({p}, {p}, 1)
        ON CONFLICT(user_id, period) DO UPDATE SET
            invoke_count = invoke_count + 1
        """,
        (user_id, period),
    )
    row = _fetchone(
        conn,
        f"SELECT invoke_count FROM user_server_invoke_usage WHERE user_id = {p} AND period = {p}",
        (user_id, period),
    )
    conn.commit()
    conn.close()
    return int(row["invoke_count"]) if row else 0


def get_server_invoke_count(user_id: str, period: str | None = None) -> int:
    period = period or current_usage_period()
    conn = get_db()
    p = _param_style()
    row = _fetchone(
        conn,
        f"SELECT invoke_count FROM user_server_invoke_usage WHERE user_id = {p} AND period = {p}",
        (user_id, period),
    )
    conn.close()
    return int(row["invoke_count"]) if row else 0


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


PRESENCE_LABELS = {
    "active": "Active",
    "afk": "AFK",
    "offline": "Offline",
}


def resolve_agent_presence(
    last_seen_at: str | None,
    presence_status: str | None,
    threshold: int | None = None,
    now_dt: datetime | None = None,
) -> dict:
    manual = (presence_status or "").strip().lower()
    if manual in PRESENCE_LABELS:
        return {
            "presence": manual,
            "presence_mode": "manual",
            "presence_label": PRESENCE_LABELS[manual],
            "online": manual == "active",
        }

    threshold = threshold if threshold is not None else config.AGENT_ONLINE_THRESHOLD_SECONDS
    now_dt = now_dt or datetime.now(timezone.utc)
    seen_dt = _parse_iso(last_seen_at)
    auto_active = bool(seen_dt and (now_dt - seen_dt).total_seconds() <= threshold)
    presence = "active" if auto_active else "offline"
    return {
        "presence": presence,
        "presence_mode": "auto",
        "presence_label": PRESENCE_LABELS[presence],
        "online": auto_active,
    }


def set_agent_presence(api_key: str, status: str) -> dict | None:
    status = status.strip().lower()
    if status not in ("auto", *PRESENCE_LABELS.keys()):
        return None
    agent = get_external_agent_details(api_key)
    if not agent or not agent.get("is_active"):
        return None
    stored = None if status == "auto" else status
    conn = get_db()
    p = _param_style()
    _execute(conn, f"UPDATE external_agents SET presence_status = {p} WHERE id = {p}", (stored, agent["id"]))
    conn.commit()
    conn.close()
    resolved = resolve_agent_presence(agent.get("last_seen_at"), stored)
    return {
        "name": agent["name"],
        "presence_setting": status,
        **resolved,
    }


def get_external_agents_status() -> list[dict]:
    conn = get_db()
    external_rows = _fetchall(
        conn,
        """SELECT e.id, e.name, e.created_at, e.last_seen_at, e.presence_status, e.is_active, a.slug AS overview_slug
           FROM external_agents e
           LEFT JOIN articles a ON a.id = e.overview_article_id
           ORDER BY e.name ASC""",
    )
    builtin_rows = []
    if _table_exists(conn, "builtin_agents"):
        builtin_rows = _fetchall(
            conn,
            """SELECT b.id, b.name, b.created_at, b.last_seen_at, b.last_action, b.last_action_at, a.slug AS overview_slug
               FROM builtin_agents b
               LEFT JOIN articles a ON a.id = b.overview_article_id
               ORDER BY b.name ASC""",
        )
    conn.close()

    threshold = config.AGENT_ONLINE_THRESHOLD_SECONDS
    now_dt = datetime.now(timezone.utc)
    agents = []

    for row in builtin_rows:
        overview_slug = row.get("overview_slug")
        agents.append({
            "id": row["id"],
            "name": row["name"],
            "role": "builtin",
            "created_at": row["created_at"],
            "last_seen_at": row.get("last_seen_at"),
            "last_action": row.get("last_action"),
            "last_action_at": row.get("last_action_at"),
            "builtin": True,
            "presence": "active",
            "presence_mode": "builtin",
            "presence_label": PRESENCE_LABELS["active"],
            "online": True,
            "overview_slug": overview_slug,
            "overview_url": f"/wiki/{overview_slug}" if overview_slug else None,
        })

    for row in external_rows:
        if not row.get("is_active"):
            continue
        last_seen = row.get("last_seen_at")
        overview_slug = row.get("overview_slug")
        presence = resolve_agent_presence(last_seen, row.get("presence_status"), threshold, now_dt)
        agents.append({
            "id": row["id"],
            "name": row["name"],
            "role": "external",
            "created_at": row["created_at"],
            "last_seen_at": last_seen,
            "builtin": False,
            "overview_slug": overview_slug,
            "overview_url": f"/wiki/{overview_slug}" if overview_slug else None,
            **presence,
        })

    order = {"active": 0, "afk": 1, "offline": 2}
    agents.sort(
        key=lambda a: (
            0 if a.get("builtin") else 1,
            order.get(a.get("presence", "offline"), 9),
            a.get("last_seen_at") or "",
            a["name"],
        )
    )
    return agents


def get_external_agents_by_user_id(user_id: str) -> list[dict]:
    conn = get_db()
    rows = _fetchall(
        conn,
        """SELECT e.id, e.name, e.created_at, e.last_seen_at, e.presence_status, e.is_active, a.slug AS overview_slug
           FROM external_agents e
           LEFT JOIN articles a ON a.id = e.overview_article_id
           WHERE e.user_id = """ + _param_style() + """ AND e.is_active = 1
           ORDER BY e.created_at DESC""",
        (user_id,),
    )
    conn.close()

    agents = []
    for row in rows:
        overview_slug = row.get("overview_slug")
        presence = resolve_agent_presence(row.get("last_seen_at"), row.get("presence_status"))
        agents.append({
            "id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "last_seen_at": row.get("last_seen_at"),
            "overview_slug": overview_slug,
            "overview_url": f"/wiki/{overview_slug}" if overview_slug else None,
            **presence,
        })
    return agents


def link_external_agent_to_user(api_key: str, user_id: str) -> str | None:
    agent = get_external_agent_details(api_key)
    if not agent or not agent.get("is_active"):
        return None
    existing_user = agent.get("user_id")
    if existing_user and existing_user != user_id:
        return "conflict"
    if existing_user == user_id:
        return "already"
    conn = get_db()
    p = _param_style()
    _execute(
        conn,
        f"UPDATE external_agents SET user_id = {p} WHERE id = {p} AND user_id IS NULL",
        (user_id, agent["id"]),
    )
    conn.commit()
    conn.close()
    return "linked"


def get_external_agent_by_name(name: str) -> dict | None:
    conn = get_db()
    p = _param_style()
    row = _fetchone(
        conn,
        f"""SELECT e.id, e.name, e.created_at, e.last_seen_at, e.presence_status, e.is_active, a.slug AS overview_slug
            FROM external_agents e
            LEFT JOIN articles a ON a.id = e.overview_article_id
            WHERE LOWER(e.name) = LOWER({p}) AND e.is_active = 1""",
        (name.strip(),),
    )
    conn.close()
    if not row:
        return None
    overview_slug = row.get("overview_slug")
    presence = resolve_agent_presence(row.get("last_seen_at"), row.get("presence_status"))
    return {
        "id": row["id"],
        "name": row["name"],
        "created_at": row["created_at"],
        "last_seen_at": row.get("last_seen_at"),
        "overview_slug": overview_slug,
        "overview_url": f"/wiki/{overview_slug}" if overview_slug else None,
        **presence,
    }


def get_external_agent_details(api_key: str) -> dict | None:
    conn = get_db()
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    row = _fetchone(
        conn,
        """SELECT e.id, e.name, e.created_at, e.is_active, e.last_seen_at, e.presence_status,
                  e.overview_article_id, e.user_id, a.slug AS overview_slug
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


def get_articles_needing_review() -> list[dict]:
    """Get articles submitted by external agents that haven't been reviewed yet."""
    conn = get_db()
    p = _param_style()
    rows = _fetchall(
        conn,
        "SELECT id, title, slug, content, updated_at FROM articles WHERE needs_review = 1 AND article_kind != 'agent_overview' ORDER BY updated_at ASC LIMIT 5",
    )
    conn.close()
    return rows


def clear_needs_review(article_id: int):
    """Mark an article as reviewed."""
    conn = get_db()
    p = _param_style()
    _execute(conn, f"UPDATE articles SET needs_review = 0 WHERE id = {p}", (article_id,))
    conn.commit()
    conn.close()


def queue_pending_topic(topic: str, source_article_id: int | None = None, category: str = "science") -> bool:
    """Add a topic to the pending queue if not already queued or written."""
    conn = get_db()
    p = _param_style()
    ts = now()
    existing = _fetchone(conn, f"SELECT id FROM articles WHERE slug = {p}", (slugify(topic),))
    if existing:
        conn.close()
        return False
    existing = _fetchone(conn, f"SELECT id FROM pending_topics WHERE topic = {p}", (topic,))
    if existing:
        conn.close()
        return False
    _execute(
        conn,
        f"INSERT INTO pending_topics (topic, source_article_id, category, queued_at) VALUES ({p}, {p}, {p}, {p})",
        (topic, source_article_id, category, ts),
    )
    conn.commit()
    conn.close()
    return True


def pop_pending_topic() -> tuple[str, str] | None:
    """Get the oldest unpicked pending topic and mark it as picked."""
    import time
    conn = get_db()
    p = _param_style()
    for attempt in range(5):
        try:
            row = _fetchone(
                conn,
                "SELECT id, topic, category FROM pending_topics WHERE picked_at IS NULL ORDER BY RANDOM() LIMIT 1",
            )
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < 4:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    if not row:
        conn.close()
        return None
    ts = now()
    for attempt in range(5):
        try:
            _execute(conn, f"UPDATE pending_topics SET picked_at = {p} WHERE id = {p}", (ts, row["id"]))
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < 4:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    conn.commit()
    conn.close()
    return row["topic"], row["category"]


def get_pending_topic_count() -> int:
    conn = get_db()
    row = _fetchone(conn, "SELECT COUNT(*) AS cnt FROM pending_topics WHERE picked_at IS NULL")
    conn.close()
    return row["cnt"] if row else 0


def parse_see_also(content: str) -> list[str]:
    """Extract [[wikilink]] topics from a See also section."""
    import re
    topics = []
    see_also_match = re.search(r'##\s*See\s+[Aa]lso\s*\n(.*?)(?=\n##\s|\Z)', content, re.DOTALL)
    if not see_also_match:
        return topics
    section = see_also_match.group(1)
    for match in re.finditer(r'\[\[([^\]]+)\]\]', section):
        topic = match.group(1).strip()
        if topic:
            topics.append(topic)
    return topics


def log_agent_action(agent_name: str, action: str, article_id: int | None = None, details: str = ""):
    conn = get_db()
    ts = now()
    p = _param_style()
    _execute(conn, f"INSERT INTO agent_logs (agent_name, action, article_id, details, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
             (agent_name, action, article_id, details, ts))
    conn.commit()
    conn.close()


def count_improvements(article_id: int) -> int:
    """Count how many times Quinn has improved a given article."""
    conn = get_db()
    p = _param_style()
    row = _fetchone(
        conn,
        f"SELECT COUNT(*) as cnt FROM agent_logs WHERE article_id = {p} "
        f"AND agent_name = 'Quality Improver Quinn' AND action = 'improve_article'",
        (article_id,),
    )
    conn.close()
    return row["cnt"] if row else 0


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
           WHERE (a.article_kind = 'encyclopedia' OR a.article_kind IS NULL)
           ORDER BY r.timestamp DESC LIMIT {p}""",
        (limit,))
    conn.close()
    return rows


def get_aitool_recent_changes(limit: int = 20) -> list[dict]:
    conn = get_db()
    p = _param_style()
    rows = _fetchall(
        conn,
        f"""SELECT r.id, r.article_id, a.title, a.slug, r.agent_name, r.summary, r.timestamp
           FROM revisions r JOIN articles a ON r.article_id = a.id
           WHERE a.article_kind = 'aitool'
           ORDER BY r.timestamp DESC LIMIT {p}""",
        (limit,),
    )
    conn.close()
    return rows


def get_aitools(limit: int | None = None) -> list[dict]:
    conn = get_db()
    query = (
        "SELECT id, title, slug, updated_at, article_kind FROM articles "
        "WHERE article_kind = 'aitool' "
        "ORDER BY updated_at DESC"
    )
    if limit is not None:
        query += f" LIMIT {_param_style()}"
        rows = _fetchall(conn, query, (limit,))
    else:
        rows = _fetchall(conn, query)
    conn.close()
    return rows


def get_encyclopedia_articles(limit: int | None = None) -> list[dict]:
    conn = get_db()
    query = (
        "SELECT id, title, slug, updated_at, article_kind FROM articles "
        "WHERE article_kind = 'encyclopedia' OR article_kind IS NULL "
        "ORDER BY updated_at DESC"
    )
    if limit is not None:
        query += f" LIMIT {_param_style()}"
        rows = _fetchall(conn, query, (limit,))
    else:
        rows = _fetchall(conn, query)
    conn.close()
    return rows


def get_migration_status() -> dict:
    from migrations.runner import get_migration_status as _status

    return _status()


def search_aitools(query: str, limit: int = 25) -> list[dict]:
    q = query.strip()
    if not q or len(q) < 2:
        return []
    conn = get_db()
    p = _param_style()
    pattern = f"%{q}%"
    if config.is_postgres():
        rows = _fetchall(
            conn,
            f"""SELECT id, title, slug, updated_at, article_kind
                FROM articles
                WHERE article_kind = 'aitool'
                  AND (title ILIKE {p} OR content ILIKE {p})
                ORDER BY updated_at DESC
                LIMIT {p}""",
            (pattern, pattern, limit),
        )
    else:
        rows = _fetchall(
            conn,
            f"""SELECT id, title, slug, updated_at, article_kind
                FROM articles
                WHERE article_kind = 'aitool'
                  AND (title LIKE {p} OR content LIKE {p})
                ORDER BY updated_at DESC
                LIMIT {p}""",
            (pattern, pattern, limit),
        )
    conn.close()
    return rows


def check_aitool_title(title: str) -> dict:
    slug = slugify(title)
    existing = get_article(slug)
    if existing and existing.get("article_kind") == "agent_overview":
        existing = None
    conn = get_db()
    p = _param_style()
    pattern = f"%{title.strip()}%"
    if config.is_postgres():
        similar = _fetchall(
            conn,
            f"""SELECT title, slug FROM articles
                WHERE article_kind = 'aitool'
                  AND title ILIKE {p}
                ORDER BY title ASC LIMIT 10""",
            (pattern,),
        )
    else:
        similar = _fetchall(
            conn,
            f"""SELECT title, slug FROM articles
                WHERE article_kind = 'aitool'
                  AND title LIKE {p}
                ORDER BY title ASC LIMIT 10""",
            (pattern,),
        )
    conn.close()
    similar = [s for s in similar if s["slug"] != slug]
    return {
        "title": title,
        "slug": slug,
        "exists": existing is not None,
        "existing_slug": existing["slug"] if existing else None,
        "similar": similar,
    }


def search_articles(query: str, limit: int = 25) -> list[dict]:
    q = query.strip()
    if not q or len(q) < 2:
        return []
    conn = get_db()
    p = _param_style()
    pattern = f"%{q}%"
    if config.is_postgres():
        rows = _fetchall(
            conn,
            f"""SELECT id, title, slug, updated_at, article_kind
                FROM articles
                WHERE (article_kind = 'encyclopedia' OR article_kind IS NULL)
                  AND (title ILIKE {p} OR content ILIKE {p})
                ORDER BY updated_at DESC
                LIMIT {p}""",
            (pattern, pattern, limit),
        )
    else:
        rows = _fetchall(
            conn,
            f"""SELECT id, title, slug, updated_at, article_kind
                FROM articles
                WHERE (article_kind = 'encyclopedia' OR article_kind IS NULL)
                  AND (title LIKE {p} OR content LIKE {p})
                ORDER BY updated_at DESC
                LIMIT {p}""",
            (pattern, pattern, limit),
        )
    conn.close()
    return rows


def check_article_title(title: str) -> dict:
    slug = slugify(title)
    existing = get_article(slug)
    conn = get_db()
    p = _param_style()
    pattern = f"%{title.strip()}%"
    if config.is_postgres():
        similar = _fetchall(
            conn,
            f"""SELECT title, slug FROM articles
                WHERE (article_kind = 'encyclopedia' OR article_kind IS NULL)
                  AND title ILIKE {p}
                ORDER BY title ASC LIMIT 10""",
            (pattern,),
        )
    else:
        similar = _fetchall(
            conn,
            f"""SELECT title, slug FROM articles
                WHERE (article_kind = 'encyclopedia' OR article_kind IS NULL)
                  AND title LIKE {p}
                ORDER BY title ASC LIMIT 10""",
            (pattern,),
        )
    conn.close()
    if existing and existing.get("article_kind") == "agent_overview":
        existing = None
    similar = [s for s in similar if s["slug"] != slug]
    return {
        "title": title,
        "slug": slug,
        "exists": existing is not None,
        "existing_slug": existing["slug"] if existing else None,
        "similar": similar,
    }


def get_external_agent_by_id(agent_id: int) -> dict | None:
    conn = get_db()
    row = _fetchone(
        conn,
        f"""SELECT e.id, e.name, e.created_at, e.is_active, e.webhook_url, a.slug AS overview_slug
            FROM external_agents e
            LEFT JOIN articles a ON a.id = e.overview_article_id
            WHERE e.id = {_param_style()} AND e.is_active = 1""",
        (agent_id,),
    )
    conn.close()
    return row


def get_agent_webhook_url(agent_id: int) -> str | None:
    conn = get_db()
    row = _fetchone(
        conn,
        f"SELECT webhook_url FROM external_agents WHERE id = {_param_style()} AND is_active = 1",
        (agent_id,),
    )
    conn.close()
    if not row:
        return None
    url = (row.get("webhook_url") or "").strip()
    return url or None


def set_agent_webhook(agent_id: int, webhook_url: str | None) -> bool:
    conn = get_db()
    p = _param_style()
    _execute(conn, f"UPDATE external_agents SET webhook_url = {p} WHERE id = {p}", (webhook_url, agent_id))
    conn.commit()
    conn.close()
    return True


def get_external_agent_activity(agent_id: int, limit: int = 20) -> list[dict]:
    agent = get_external_agent_by_id(agent_id)
    if not agent:
        return []
    name = agent["name"]
    conn = get_db()
    p = _param_style()
    like = f"{name}%"
    logs = _fetchall(
        conn,
        f"""SELECT 'log' AS source, action AS kind, details AS summary, timestamp, article_id
            FROM agent_logs
            WHERE agent_name LIKE {p}
            ORDER BY timestamp DESC
            LIMIT {p}""",
        (like, limit),
    )
    revisions = _fetchall(
        conn,
        f"""SELECT 'revision' AS source, 'edit' AS kind, r.summary, r.timestamp, r.article_id,
                   a.title, a.slug
            FROM revisions r
            JOIN articles a ON a.id = r.article_id
            WHERE r.agent_name LIKE {p}
            ORDER BY r.timestamp DESC
            LIMIT {p}""",
        (like, limit),
    )
    conn.close()

    activity = []
    for row in logs:
        activity.append({
            "source": row["source"],
            "kind": row["kind"],
            "summary": row.get("summary") or row["kind"],
            "timestamp": row["timestamp"],
            "article_id": row.get("article_id"),
            "slug": None,
            "title": None,
        })
    for row in revisions:
        activity.append({
            "source": row["source"],
            "kind": row["kind"],
            "summary": row.get("summary") or "Edited article",
            "timestamp": row["timestamp"],
            "article_id": row.get("article_id"),
            "slug": row.get("slug"),
            "title": row.get("title"),
        })

    activity.sort(key=lambda item: item["timestamp"], reverse=True)
    return activity[:limit]
