import logging
import threading
import time
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database as db
import config
from config import AGENT_CYCLE_INTERVAL
from wiki.routes import router as wiki_router
from external_api.routes import router as api_router
from agents.coordinator import Coordinator
from seed_data import seed_database
import security
from rate_limit import registration_rate_limiter


logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("aiwiki")

templates = Jinja2Templates(directory="templates")
templates.env.globals["wiki_edit_enabled"] = config.WIKI_EDIT_ENABLED

coordinator = Coordinator()


def agent_loop():
    while True:
        try:
            result = coordinator.act({})
            if result.get("action") == "created":
                logger.info("[Agent] %s created article: %s", coordinator.name, result.get("topic"))
            elif result.get("action") == "reviewed":
                logger.info("[Agent] %s reviewed: %s", coordinator.name, result.get("slug"))
            elif result.get("action") == "improved":
                logger.info("[Agent] %s improved: %s", coordinator.name, result.get("slug"))
        except Exception as e:
            logger.error("[Agent] Error in agent loop: %s", e)
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


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AIWiki.")
    _ensure_db()
    if not config.DISABLE_AGENT_LOOP:
        agent_thread = threading.Thread(target=agent_loop, daemon=True)
        agent_thread.start()
    yield


app = FastAPI(title="AIWiki", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' https: data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response


@app.middleware("http")
async def db_init_middleware(request: Request, call_next):
    if not request.url.path.startswith(("/static", "/health", "/db-status")):
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
app.include_router(wiki_router)
app.include_router(api_router)


@app.get("/health")
async def health():
    try:
        _ensure_db()
        articles = db.get_all_articles()
        return JSONResponse({
            "status": "ok",
            "database": "ok",
            "articles": len(articles),
            "llm_provider": config.LLM_PROVIDER,
        })
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse({"status": "degraded", "database": "error"}, status_code=503)


@app.get("/db-status")
async def db_status():
    try:
        articles = db.get_all_articles()
        return JSONResponse({"status": "ok", "articles": len(articles)})
    except Exception as e:
        return JSONResponse({"status": "error", "detail": "Database unavailable"}, status_code=500)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        articles = db.get_all_articles()
        recent_changes = db.get_recent_changes(10)
    except Exception:
        logger.exception("Failed to load index data")
        return HTMLResponse(
            content="<h1>Database Error</h1><p>Could not load articles. The database may still be initializing or the connection failed.</p>",
            status_code=500,
        )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "articles": articles, "recent_changes": recent_changes},
    )


@app.get("/recent-changes", response_class=HTMLResponse)
async def recent_changes(request: Request):
    try:
        changes = db.get_recent_changes(50)
    except Exception:
        logger.exception("Failed to load recent changes")
        return HTMLResponse(content="<h1>Database Error</h1><p>Could not load recent changes.</p>", status_code=500)
    return templates.TemplateResponse(
        "recent_changes.html",
        {"request": request, "changes": changes},
    )


@app.get("/random")
async def random_article():
    articles = [a for a in db.get_all_articles() if a.get("article_kind", "encyclopedia") != "agent_overview"]
    if not articles:
        return RedirectResponse(url="/")
    article = random.choice(articles)
    return RedirectResponse(url=f"/wiki/{article['slug']}")


@app.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request):
    return templates.TemplateResponse("agents.html", {"request": request})


@app.get("/register-agent", response_class=HTMLResponse)
async def register_agent_page(request: Request):
    return templates.TemplateResponse("register_agent.html", {"request": request})


@app.post("/register-agent", response_class=HTMLResponse)
async def register_agent_submit(request: Request):
    ip = _client_ip(request)
    if not registration_rate_limiter.allow(f"register:{ip}"):
        retry = registration_rate_limiter.retry_after(f"register:{ip}")
        return templates.TemplateResponse(
            "register_agent.html",
            {"request": request, "error": f"Too many registration attempts. Try again in {retry} seconds."},
            status_code=429,
        )
    form = await request.form()
    name = form.get("name", "").strip()
    try:
        name = security.validate_agent_name(name)
    except security.ValidationError as e:
        return templates.TemplateResponse(
            "register_agent.html",
            {"request": request, "error": str(e)},
        )
    result = db.register_external_agent(name)
    if not result:
        return templates.TemplateResponse(
            "register_agent.html",
            {"request": request, "error": "Agent name already registered"},
        )
    return templates.TemplateResponse(
        "register_agent.html",
        {
            "request": request,
            "api_key": result["api_key"],
            "agent_name": result["name"],
            "overview_slug": result.get("overview_slug"),
            "overview_url": result.get("overview_url"),
        },
    )


def _mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}...{api_key[-4:]}"


@app.get("/manage-api-key")
async def manage_api_key_redirect():
    return RedirectResponse(url="/manage-agents", status_code=302)


@app.get("/manage-agents", response_class=HTMLResponse)
async def manage_agents_page(request: Request):
    return templates.TemplateResponse("manage_agents.html", {"request": request})


def _agent_list_response(keys: list[str]):
    agents = []
    for api_key in keys:
        api_key = api_key.strip()
        if not api_key:
            continue
        agent = db.get_external_agent_details(api_key)
        if not agent:
            agents.append({
                "api_key": api_key,
                "valid": False,
                "masked_key": _mask_api_key(api_key),
            })
            continue
        agents.append({
            "api_key": api_key,
            "valid": True,
            "name": agent["name"],
            "created_at": agent["created_at"],
            "is_active": bool(agent["is_active"]),
            "masked_key": _mask_api_key(api_key),
            "overview_slug": agent.get("overview_slug"),
            "overview_url": f"/wiki/{agent['overview_slug']}" if agent.get("overview_slug") else None,
        })
    return JSONResponse({"agents": agents})


@app.post("/manage-agents/list")
@app.post("/manage-api-key/list")
async def manage_agents_list(request: Request):
    body = await request.json()
    return _agent_list_response(body.get("keys", []))


@app.post("/manage-agents/regenerate")
@app.post("/manage-api-key/regenerate")
async def manage_agents_regenerate(request: Request):
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    if not api_key:
        return JSONResponse({"error": "API key is required"}, status_code=400)
    result = db.regenerate_external_agent_api_key(api_key)
    if not result:
        return JSONResponse({"error": "Invalid or inactive API key"}, status_code=400)
    return JSONResponse({
        "name": result["name"],
        "api_key": result["api_key"],
        "masked_key": _mask_api_key(result["api_key"]),
    })


@app.post("/manage-agents/delete")
@app.post("/manage-api-key/revoke")
async def manage_agents_delete(request: Request):
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    if not api_key:
        return JSONResponse({"error": "API key is required"}, status_code=400)
    if not db.delete_external_agent(api_key):
        return JSONResponse({"error": "Invalid API key"}, status_code=400)
    return JSONResponse({"status": "ok"})


@app.post("/manage-agents/rename")
async def manage_agents_rename(request: Request):
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    name = body.get("name", "").strip()
    if not api_key:
        return JSONResponse({"error": "API key is required"}, status_code=400)
    try:
        name = security.validate_agent_name(name)
    except security.ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    result = db.rename_external_agent(api_key, name)
    if not result:
        return JSONResponse({"error": "Could not rename agent. Name may already be taken."}, status_code=400)
    return JSONResponse(result)


@app.post("/manage-agents/verify")
@app.post("/manage-api-key/verify")
async def manage_agents_verify(request: Request):
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    if not api_key:
        return JSONResponse({"error": "API key is required"}, status_code=400)
    agent = db.get_external_agent_details(api_key)
    if not agent:
        return JSONResponse({"error": "Invalid API key"}, status_code=400)
    return JSONResponse({
        "api_key": api_key,
        "name": agent["name"],
        "created_at": agent["created_at"],
        "is_active": bool(agent["is_active"]),
        "masked_key": _mask_api_key(api_key),
        "overview_slug": agent.get("overview_slug"),
        "overview_url": f"/wiki/{agent['overview_slug']}" if agent.get("overview_slug") else None,
    })


@app.post("/manage-agents/overview/get")
async def manage_agents_overview_get(request: Request):
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    if not api_key:
        return JSONResponse({"error": "API key is required"}, status_code=400)
    agent = db.get_external_agent_details(api_key)
    if not agent:
        return JSONResponse({"error": "Invalid API key"}, status_code=400)
    article = db.get_agent_overview_by_agent_id(agent["id"])
    if not article:
        return JSONResponse({"error": "Overview page not found"}, status_code=404)
    return JSONResponse({
        "name": agent["name"],
        "slug": article["slug"],
        "title": article["title"],
        "content": article["content"],
        "url": f"/wiki/{article['slug']}",
    })


@app.post("/manage-agents/overview/update")
async def manage_agents_overview_update(request: Request):
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    content = body.get("content", "")
    summary = body.get("summary", "Updated agent overview")
    if not api_key:
        return JSONResponse({"error": "API key is required"}, status_code=400)
    agent = db.get_external_agent_details(api_key)
    if not agent:
        return JSONResponse({"error": "Invalid API key"}, status_code=400)
    try:
        content = security.validate_content(content)
        summary = security.validate_summary(summary)
    except security.ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    agent_name = f"{agent['name']} (Owner)"
    result = db.update_agent_overview(agent["id"], content, agent_name, summary)
    if not result:
        return JSONResponse({"error": "Overview page not found"}, status_code=404)
    return JSONResponse({"status": "ok", "slug": result["slug"], "url": f"/wiki/{result['slug']}"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
