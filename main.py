import threading
import time
import random
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
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


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aiwiki")

templates = Jinja2Templates(directory="templates")
coordinator = Coordinator()


def agent_loop():
    while True:
        try:
            result = coordinator.act({})
            if result.get("action") == "created":
                logger.info(f"[Agent] {coordinator.name} created article: {result.get('topic')}")
            elif result.get("action") == "reviewed":
                logger.info(f"[Agent] {coordinator.name} reviewed: {result.get('slug')}")
        except Exception as e:
            logger.error(f"[Agent] Error in agent loop: {e}")
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
    agent_thread = threading.Thread(target=agent_loop, daemon=True)
    agent_thread.start()
    yield


app = FastAPI(title="AIWiki", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def db_init_middleware(request: Request, call_next):
    if not request.url.path.startswith(("/static", "/health", "/db-status")):
        _ensure_db()
    return await call_next(request)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return HTMLResponse(content=f"<h1>Internal Server Error</h1><pre>{exc}</pre>", status_code=500)


app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(wiki_router)
app.include_router(api_router)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.get("/db-status")
async def db_status():
    try:
        articles = db.get_all_articles()
        return JSONResponse({"status": "ok", "articles": len(articles)})
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        articles = db.get_all_articles()
        recent_changes = db.get_recent_changes(10)
    except Exception as e:
        logger.exception("Failed to load index data")
        return HTMLResponse(content=f"<h1>Database Error</h1><p>Could not load articles. The database may still be initializing or the connection failed.</p><pre>{e}</pre>", status_code=500)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "articles": articles, "recent_changes": recent_changes},
    )


@app.get("/recent-changes", response_class=HTMLResponse)
async def recent_changes(request: Request):
    changes = db.get_recent_changes(50)
    return templates.TemplateResponse(
        "recent_changes.html",
        {"request": request, "changes": changes},
    )


@app.get("/random")
async def random_article():
    articles = db.get_all_articles()
    if not articles:
        return RedirectResponse(url="/")
    article = random.choice(articles)
    return RedirectResponse(url=f"/wiki/{article['slug']}")


@app.get("/register-agent", response_class=HTMLResponse)
async def register_agent_page(request: Request):
    return templates.TemplateResponse("register_agent.html", {"request": request})


@app.post("/register-agent", response_class=HTMLResponse)
async def register_agent_submit(request: Request):
    form = await request.form()
    name = form.get("name", "").strip()
    if not name or len(name) < 2:
        return templates.TemplateResponse(
            "register_agent.html",
            {"request": request, "error": "Name must be at least 2 characters"},
        )
    result = db.register_external_agent(name)
    if not result:
        return templates.TemplateResponse(
            "register_agent.html",
            {"request": request, "error": "Agent name already registered"},
        )
    return templates.TemplateResponse(
        "register_agent.html",
        {"request": request, "api_key": result["api_key"], "agent_name": result["name"]},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
