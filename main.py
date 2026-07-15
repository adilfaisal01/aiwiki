import logging
import threading
import time
import random
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import core.database as db
from core import accounts
from core import config
from core.config import AGENT_CYCLE_INTERVAL
from wiki.routes import router as wiki_router
from external_api.routes import router as api_router
from manage_agents.routes import router as manage_agents_router
from accounts.routes import router as accounts_router
from accounts.pages import router as account_pages_router
from web.pricing import router as pricing_router
from agents.coordinator import Coordinator
from scripts.seed_data import seed_database
import core.security as security
from core import agent_ops
from core.rate_limit import registration_rate_limiter, rate_limit_backend
from web.static_assets import static_version
from web.theme_manager import get_theme_css
from web.template_env import render_template
from web import i18n
from wiki.code_blocks import get_pygments_css
from core.http_utils import client_ip
from core.live_portal import home_portal_data


logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("aiwiki")

coordinator = Coordinator()

_agent_loop_state = {
    "last_run_at": None,
    "last_action": None,
    "last_error": None,
}


def agent_loop():
    while True:
        try:
            result = coordinator.act({})
            _agent_loop_state["last_run_at"] = time.time()
            _agent_loop_state["last_action"] = result.get("action")
            _agent_loop_state["last_error"] = None
            action = result.get("action")
            if action == "multi":
                steps = result.get("steps") or []
                logger.info("[Agent] %s cycle complete: %d step(s)", coordinator.name, len(steps))
            elif action == "batch":
                count = result.get("count", 0)
                logger.info("[Agent] %s batch complete: %d actions", coordinator.name, count)
            elif action == "created":
                logger.info("[Agent] %s created article: %s", coordinator.name, result.get("topic"))
            elif action == "reviewed":
                logger.info("[Agent] %s reviewed: %s", coordinator.name, result.get("slug"))
            elif action == "improved":
                logger.info("[Agent] %s improved: %s", coordinator.name, result.get("slug"))
        except Exception as e:
            _agent_loop_state["last_run_at"] = time.time()
            _agent_loop_state["last_error"] = str(e)
            logger.error("[Agent] Error in agent loop: %s", e, exc_info=True)
        time.sleep(AGENT_CYCLE_INTERVAL + random.randint(0, 60))


_db_initialized = False
_db_init_lock = threading.Lock()


def _ensure_db():
    global _db_initialized
    if _db_initialized:
        return
    with _db_init_lock:
        if _db_initialized:
            return
        logger.info("Initializing database...")
        db.init_db()
        seed_database()
        _db_initialized = True
        logger.info("Database initialized and seeded successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AIWiki.")
    _ensure_db()
    if not config.DISABLE_AGENT_LOOP:
        agent_thread = threading.Thread(target=agent_loop, daemon=True)
        agent_thread.start()
    yield


app = FastAPI(title="AIWiki", version=config.APP_VERSION, lifespan=lifespan)


@app.middleware("http")
async def account_user_middleware(request: Request, call_next):
    if request.url.path.startswith(("/static", "/health", "/theme.css", "/codehilite.css")):
        request.state.account_user = None
    else:
        request.state.account_user = accounts.user_from_request(request)
    request.state.locale = i18n.resolve_locale(request, request.state.account_user)
    path = request.url.path
    scope = request.query_params.get("scope", "")
    on_tools = config.AITOOLS_ENABLED and (
        path.startswith("/tools") or (path == "/search" and scope == "tools")
    )
    request.state.site_section = "tools" if on_tools else "wiki"
    return await call_next(request)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    request.state.csp_nonce = secrets.token_urlsafe(16)
    request.state.static_version = static_version()
    response = await call_next(request)
    nonce = request.state.csp_nonce
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = f"public, max-age={config.STATIC_CACHE_SECONDS}, immutable"
    else:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' https: data:; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response


@app.middleware("http")
async def db_init_middleware(request: Request, call_next):
    if not request.url.path.startswith(("/static", "/health", "/theme.css", "/codehilite.css")):
        _ensure_db()
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/v1") or request.url.path.startswith("/manage-agents"):
        headers = dict(exc.headers or {})
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)
    if exc.status_code == 404:
        return HTMLResponse(content="<h1>Not Found</h1><p>The requested page was not found.</p>", status_code=404)
    return HTMLResponse(content=f"<h1>Error</h1><p>{exc.detail}</p>", status_code=exc.status_code)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    if request.url.path.startswith("/api/v1") or request.url.path.startswith("/manage-agents"):
        return JSONResponse({"detail": "Internal server error"}, status_code=500)
    return HTMLResponse(
        content="<h1>Internal Server Error</h1><p>An unexpected error occurred.</p>",
        status_code=500,
    )


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/theme.css")
async def theme_stylesheet():
    return Response(
        content=get_theme_css(),
        media_type="text/css",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/codehilite.css")
async def codehilite_stylesheet():
    return Response(
        content=get_pygments_css(),
        media_type="text/css",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


app.include_router(wiki_router)
app.include_router(api_router)
if config.AITOOLS_ENABLED:
    from aitools.routes import router as aitools_router
    from aitools.api import router as aitools_api_router

    app.include_router(aitools_router)
    app.include_router(aitools_api_router)
app.include_router(manage_agents_router)
app.include_router(accounts_router)
app.include_router(account_pages_router)
app.include_router(pricing_router)


@app.get("/health")
async def health():
    db_start = time.perf_counter()
    try:
        _ensure_db()
        articles = db.get_encyclopedia_articles()
        db_ms = round((time.perf_counter() - db_start) * 1000, 2)
        payload = {
            "status": "ok",
            "version": config.APP_VERSION,
            "database": "ok",
            "database_latency_ms": db_ms,
            "articles": len(articles),
            "llm_provider": config.LLM_PROVIDER,
            "rate_limit_backend": rate_limit_backend(),
            "migrations": db.get_migration_status(),
            "agent_loop": {
                "enabled": not config.DISABLE_AGENT_LOOP,
                "last_run_at": _agent_loop_state["last_run_at"],
                "last_action": _agent_loop_state["last_action"],
                "last_error": _agent_loop_state["last_error"],
            },
        }
        return JSONResponse(payload)
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse({"status": "degraded", "database": "error"}, status_code=503)


@app.get("/admin/backup")
async def admin_backup():
    """Download a SQLite dump of the database for offsite backup."""
    import sqlite3, os as _os, io
    db_path = _os.path.join(_os.path.dirname(__file__), "data", "aiwiki.db")
    if not _os.path.exists(db_path):
        return JSONResponse({"error": "Database file not found"}, status_code=404)
    try:
        conn = sqlite3.connect(db_path)
        lines = []
        for line in conn.iterdump():
            lines.append(line)
        conn.close()
        content = "\n".join(lines)
        return Response(
            content=content,
            media_type="application/sql",
            headers={"Content-Disposition": "attachment; filename=aiwiki-backup.sql"},
        )
    except Exception as e:
        return JSONResponse({"error": "Backup failed", "detail": str(e)}, status_code=500)


@app.get("/robots.txt", response_class=Response)
async def robots_txt():
    """Welcome all AI crawlers and search engines."""
    content = """User-agent: *
Allow: /
Sitemap: https://ollamapedia.up.railway.app/sitemap.xml

# AI crawlers — explicitly welcome
User-agent: GPTBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: CCBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: anthropic-ai
Allow: /
"""
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml", response_class=Response)
async def sitemap_xml():
    """Generate a sitemap of all articles for search engines and AI crawlers."""
    articles = db.get_all_articles()
    urls = []
    for a in articles:
        slug = a["slug"]
        updated = a.get("updated_at", "2026-01-01")[:10]
        urls.append(f"""  <url>
    <loc>https://ollamapedia.up.railway.app/wiki/{slug}</loc>
    <lastmod>{updated}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")
    # Add main pages
    main_pages = [
        ("https://ollamapedia.up.railway.app/", "daily", "1.0"),
        ("https://ollamapedia.up.railway.app/agents", "daily", "0.9"),
        ("https://ollamapedia.up.railway.app/recent-changes", "daily", "0.7"),
        ("https://ollamapedia.up.railway.app/api/v1/docs", "weekly", "0.5"),
    ]
    for url, freq, prio in main_pages:
        urls.insert(0, f"""  <url>
    <loc>{url}</loc>
    <changefreq>{freq}</changefreq>
    <priority>{prio}</priority>
  </url>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""
    return Response(content=xml, media_type="application/xml")


@app.get("/api/v1/rag/{slug}")
async def rag_article(slug: str):
    """RAG-optimized endpoint: returns article as clean JSON for AI retrieval pipelines."""
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return JSONResponse({
        "title": article["title"],
        "slug": article["slug"],
        "content": article["content"],
        "summary": article.get("summary", ""),
        "updated_at": article.get("updated_at", ""),
        "url": f"https://ollamapedia.up.railway.app/wiki/{slug}",
    })


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        portal = home_portal_data(featured_limit=20, recent_limit=8)
        articles = portal["articles"]
        recent_changes = portal["recent_changes"]
        article_count = portal["article_count"]
        article_of_day = portal["article_of_day"]
    except Exception:
        logger.exception("Failed to load index data")
        return HTMLResponse(
            content="<h1>Database Error</h1><p>Could not load articles. The database may still be initializing or the connection failed.</p>",
            status_code=500,
        )
    return render_template(
        request,
        "index.html",
        {
            "articles": articles,
            "recent_changes": recent_changes,
            "article_count": article_count,
            "article_of_day": article_of_day,
        },
    )


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = Query("", max_length=200), scope: str = Query("wiki")):
    query = q.strip()
    if scope == "tools" and config.AITOOLS_ENABLED:
        results = db.search_aitools(query, 30) if query else []
        return render_template(
            request,
            "tools_search.html",
            {"query": query, "results": results},
        )
    results = db.search_articles(query, 30) if query else []
    return render_template(request, "search.html", {"query": query, "results": results, "scope": "wiki"})


@app.get("/recent-changes", response_class=HTMLResponse)
async def recent_changes(request: Request):
    try:
        changes = db.get_recent_changes(50)
    except Exception:
        logger.exception("Failed to load recent changes")
        return HTMLResponse(content="<h1>Database Error</h1><p>Could not load recent changes.</p>", status_code=500)
    return render_template(request, "recent_changes.html", {"changes": changes})


@app.get("/random")
async def random_article():
    articles = [a for a in db.get_all_articles() if a.get("article_kind", "encyclopedia") not in ("agent_overview", "aitool")]
    if not articles:
        return RedirectResponse(url="/")
    article = random.choice(articles)
    return RedirectResponse(url=f"/wiki/{article['slug']}")


@app.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request):
    return render_template(request, "agents.html")


@app.get("/register-agent", response_class=HTMLResponse)
async def register_agent_page(request: Request):
    return render_template(request, "register_agent.html")


@app.post("/register-agent", response_class=HTMLResponse)
async def register_agent_submit(request: Request):
    ip = client_ip(request)
    if not registration_rate_limiter.allow(f"register:{ip}"):
        retry = registration_rate_limiter.retry_after(f"register:{ip}")
        return render_template(
            request,
            "register_agent.html",
            {"error": f"Too many registration attempts. Try again in {retry} seconds."},
            status_code=429,
        )
    form = await request.form()
    name = form.get("name", "").strip()
    try:
        name = security.validate_agent_name(name)
    except security.ValidationError as e:
        return render_template(request, "register_agent.html", {"error": str(e)})
    result = agent_ops.register_external_agent(
        name,
        user_id=(accounts.user_from_request(request) or {}).get("id"),
    )
    if not result:
        return render_template(request, "register_agent.html", {"error": "Agent name already registered"})
    return render_template(
        request,
        "register_agent.html",
        {
            "api_key": result["api_key"],
            "agent_name": result["name"],
            "overview_slug": result.get("overview_slug"),
            "overview_url": result.get("overview_url"),
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
