import threading
import time
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database as db
from config import AGENT_CYCLE_INTERVAL
from wiki.routes import router as wiki_router
from external_api.routes import router as api_router
from agents.coordinator import Coordinator
from seed_data import seed_database


templates = Jinja2Templates(directory="templates")
coordinator = Coordinator()


def agent_loop():
    while True:
        try:
            result = coordinator.act({})
            if result.get("action") == "created":
                print(f"[Agent] {coordinator.name} created article: {result.get('topic')}")
            elif result.get("action") == "reviewed":
                print(f"[Agent] {coordinator.name} reviewed: {result.get('slug')}")
        except Exception as e:
            print(f"[Agent] Error in agent loop: {e}")
        time.sleep(AGENT_CYCLE_INTERVAL + random.randint(0, 60))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    seed_database()
    thread = threading.Thread(target=agent_loop, daemon=True)
    thread.start()
    yield


app = FastAPI(title="AIWiki", version="1.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(wiki_router)
app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    articles = db.get_all_articles()
    recent_changes = db.get_recent_changes(10)
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
