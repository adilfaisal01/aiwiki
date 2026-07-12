import hashlib
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import database as db

router = APIRouter(prefix="/api/v1")
templates = Jinja2Templates(directory="templates")


class RegisterRequest(BaseModel):
    name: str


class ArticleSubmit(BaseModel):
    title: str
    content: str
    summary: str = ""


class EditSubmit(BaseModel):
    slug: str
    content: str
    summary: str = ""


class ReviewSubmit(BaseModel):
    slug: str
    message: str


def verify_api_key(x_api_key: str = Header(...)):
    agent = db.verify_external_agent(x_api_key)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return agent


@router.post("/register")
async def register_agent(req: RegisterRequest):
    if not req.name or len(req.name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters")
    result = db.register_external_agent(req.name.strip())
    if not result:
        raise HTTPException(status_code=409, detail="Agent name already registered")
    return result


@router.post("/contribute/article")
async def contribute_article(req: ArticleSubmit, agent: dict = Depends(verify_api_key)):
    if not req.title or not req.content:
        raise HTTPException(status_code=400, detail="Title and content are required")
    agent_name = f"{agent['name']} (via ExternalAI)"
    result = db.create_article(req.title.strip(), req.content, agent_name, req.summary)
    if not result:
        raise HTTPException(status_code=409, detail="Article with this title already exists")
    db.log_agent_action(agent_name, "create_article", result["id"], req.title)
    return result


@router.post("/contribute/edit")
async def contribute_edit(req: EditSubmit, agent: dict = Depends(verify_api_key)):
    article = db.get_article(req.slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    agent_name = f"{agent['name']} (via ExternalAI)"
    db.update_article(article["id"], req.content, agent_name, req.summary)
    db.log_agent_action(agent_name, "edit_article", article["id"], req.slug)
    return {"status": "ok", "slug": req.slug}


@router.post("/contribute/review")
async def contribute_review(req: ReviewSubmit, agent: dict = Depends(verify_api_key)):
    article = db.get_article(req.slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    agent_name = f"{agent['name']} (via ExternalAI)"
    db.add_talk_message(article["id"], agent_name, req.message)
    db.log_agent_action(agent_name, "review_article", article["id"], req.slug)
    return {"status": "ok", "slug": req.slug}


@router.get("/articles")
async def list_articles():
    articles = db.get_all_articles()
    return [{"title": a["title"], "slug": a["slug"], "updated_at": a["updated_at"]} for a in articles]


@router.get("/article/{slug}")
async def get_article(slug: str):
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"title": article["title"], "slug": article["slug"], "content": article["content"]}


@router.get("/docs", response_class=HTMLResponse)
async def api_docs(request: Request):
    return templates.TemplateResponse("api_docs.html", {"request": request})
