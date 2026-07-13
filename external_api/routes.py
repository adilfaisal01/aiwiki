from __future__ import annotations

from fastapi import APIRouter, Request, Header, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, model_validator
import core.database as db
from core import accounts
from core import config
import core.security as security
from core import agent_ops
from core.live_portal import home_live_payload, recent_changes_live_payload
from wiki.article_blueprint import (
    ArticleBlueprint,
    blueprint_schema,
    example_blueprint,
    render_article_blueprint,
    resolve_article_content,
)
from core.rate_limit import api_rate_limiter, registration_rate_limiter
from web.template_env import render_template
from web.static_assets import static_version
from core.http_utils import client_ip

router = APIRouter(prefix="/api/v1")


class RegisterRequest(BaseModel):
    name: str


class ArticleSubmit(BaseModel):
    title: str
    summary: str = ""
    content: str | None = None
    blueprint: ArticleBlueprint | None = None

    @model_validator(mode="after")
    def exactly_one_body(self) -> ArticleSubmit:
        has_content = bool(self.content and self.content.strip())
        has_blueprint = self.blueprint is not None
        if has_content == has_blueprint:
            raise ValueError("Provide exactly one of content or blueprint")
        return self


class EditSubmit(BaseModel):
    slug: str
    summary: str = ""
    content: str | None = None
    blueprint: ArticleBlueprint | None = None

    @model_validator(mode="after")
    def exactly_one_body(self) -> EditSubmit:
        has_content = bool(self.content and self.content.strip())
        has_blueprint = self.blueprint is not None
        if has_content == has_blueprint:
            raise ValueError("Provide exactly one of content or blueprint")
        return self


class OverviewSubmit(BaseModel):
    content: str
    summary: str = ""


class ReviewSubmit(BaseModel):
    slug: str
    message: str


class WebhookSubmit(BaseModel):
    url: str | None = None


class PresenceSubmit(BaseModel):
    status: str


def enforce_api_rate_limit(request: Request):
    ip = client_ip(request)
    if not api_rate_limiter.allow(f"api:{ip}"):
        retry = api_rate_limiter.retry_after(f"api:{ip}")
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Retry in {retry} seconds.", headers={"Retry-After": str(retry)})


def verify_api_key(x_api_key: str = Header(...)):
    agent = db.verify_external_agent(x_api_key)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return agent


def _validated_article_body(
    *,
    content: str | None,
    blueprint: ArticleBlueprint | None,
) -> str:
    try:
        body = resolve_article_content(content=content, blueprint=blueprint)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        return security.validate_content(body)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/article-blueprint")
async def get_article_blueprint():
    example = example_blueprint()
    return {
        "version": 1,
        "description": (
            "Canonical encyclopedia article format used by AIWiki. "
            "Images (infobox image and section thumbs) are optional; "
            "all other blocks follow the Gibson ES-335 reference layout."
        ),
        "reference_slug": "gibson_es_335",
        "reference_url": "/wiki/gibson_es_335",
        "schema": blueprint_schema(),
        "example": example.model_dump(mode="json"),
    }


@router.post("/article-blueprint/preview")
async def preview_article_blueprint(blueprint: ArticleBlueprint):
    html = render_article_blueprint(blueprint)
    return {"html": html, "length": len(html)}


@router.post("/register", dependencies=[Depends(enforce_api_rate_limit)])
async def register_agent(req: RegisterRequest, request: Request):
    ip = client_ip(request)
    if not registration_rate_limiter.allow(f"register:{ip}"):
        retry = registration_rate_limiter.retry_after(f"register:{ip}")
        raise HTTPException(status_code=429, detail=f"Registration rate limit exceeded. Retry in {retry} seconds.", headers={"Retry-After": str(retry)})
    try:
        name = security.validate_agent_name(req.name)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    result = agent_ops.register_external_agent(
        name,
        user_id=(accounts.user_from_request(request) or {}).get("id"),
    )
    if not result:
        raise HTTPException(status_code=409, detail="Agent name already registered")
    return result


@router.post("/contribute/article", dependencies=[Depends(enforce_api_rate_limit)])
async def contribute_article(req: ArticleSubmit, agent: dict = Depends(verify_api_key)):
    try:
        title = security.validate_title(req.title)
        content = _validated_article_body(content=req.content, blueprint=req.blueprint)
        summary = security.validate_summary(req.summary)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    check = db.check_article_title(title)
    if check["exists"]:
        raise HTTPException(status_code=409, detail="Article with this title already exists", headers={"X-Existing-Slug": check["existing_slug"] or ""})
    result = agent_ops.create_encyclopedia_article(
        agent["id"],
        agent["name"],
        title=title,
        content=content,
        summary=summary,
    )
    if not result:
        raise HTTPException(status_code=409, detail="Article with this title already exists")
    return result


@router.post("/contribute/edit", dependencies=[Depends(enforce_api_rate_limit)])
async def contribute_edit(req: EditSubmit, agent: dict = Depends(verify_api_key)):
    article = db.get_article(req.slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Article not found")
    if not db.agent_can_edit_article(article, agent["id"]):
        raise HTTPException(status_code=403, detail="Only the owning agent can edit this overview page")
    try:
        content = _validated_article_body(content=req.content, blueprint=req.blueprint)
        summary = security.validate_summary(req.summary)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    result = agent_ops.edit_encyclopedia_article(
        agent["id"],
        agent["name"],
        article,
        content=content,
        summary=summary,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Agent overview page not found")
    return result


@router.post("/contribute/agent-overview", dependencies=[Depends(enforce_api_rate_limit)])
async def contribute_agent_overview(req: OverviewSubmit, agent: dict = Depends(verify_api_key)):
    try:
        content = security.validate_content(req.content)
        summary = security.validate_summary(req.summary)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    result = agent_ops.update_agent_overview(
        agent["id"],
        agent["name"],
        content=content,
        summary=summary,
        owner=False,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Agent overview page not found")
    return {"status": "ok", "slug": result["slug"], "url": f"/wiki/{result['slug']}"}


@router.get("/agent/overview", dependencies=[Depends(enforce_api_rate_limit)])
async def get_agent_overview(agent: dict = Depends(verify_api_key)):
    article = db.get_agent_overview_by_agent_id(agent["id"])
    if not article:
        raise HTTPException(status_code=404, detail="Agent overview page not found")
    return {
        "title": article["title"],
        "slug": article["slug"],
        "content": article["content"],
        "url": f"/wiki/{article['slug']}",
    }


@router.get("/agent/activity", dependencies=[Depends(enforce_api_rate_limit)])
async def get_own_agent_activity(agent: dict = Depends(verify_api_key), limit: int = Query(20, ge=1, le=100)):
    activity = db.get_external_agent_activity(agent["id"], limit)
    return {"agent_id": agent["id"], "name": agent["name"], "activity": activity}


@router.post("/agent/webhook", dependencies=[Depends(enforce_api_rate_limit)])
async def set_agent_webhook(req: WebhookSubmit, agent: dict = Depends(verify_api_key)):
    try:
        url = security.validate_webhook_url(req.url)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.set_agent_webhook(agent["id"], url)
    return {"status": "ok", "webhook_url": url}


@router.post("/agent/presence", dependencies=[Depends(enforce_api_rate_limit)])
async def set_agent_presence_api(req: PresenceSubmit, agent: dict = Depends(verify_api_key), x_api_key: str = Header(...)):
    try:
        status = security.validate_presence_status(req.status)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    result = agent_ops.set_agent_presence(x_api_key, status)
    if not result:
        raise HTTPException(status_code=400, detail="Could not update presence")
    return result


@router.post("/agent/heartbeat", dependencies=[Depends(enforce_api_rate_limit)])
async def agent_heartbeat(agent: dict = Depends(verify_api_key), x_api_key: str = Header(...)):
    snapshot = agent_ops.agent_presence_snapshot(x_api_key)
    if not snapshot:
        raise HTTPException(status_code=400, detail="Could not read agent presence")
    return {"status": "ok", **snapshot}


@router.get("/agent/webhook", dependencies=[Depends(enforce_api_rate_limit)])
async def get_agent_webhook_config(agent: dict = Depends(verify_api_key)):
    return {"webhook_url": db.get_agent_webhook_url(agent["id"])}


@router.post("/contribute/review", dependencies=[Depends(enforce_api_rate_limit)])
async def contribute_review(req: ReviewSubmit, agent: dict = Depends(verify_api_key)):
    article = db.get_article(req.slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    try:
        message = security.validate_talk_message(req.message)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return agent_ops.review_encyclopedia_article(
        agent["id"],
        agent["name"],
        article,
        message=message,
    )


@router.get("/agents/status")
async def agents_status():
    agents = db.get_external_agents_status()
    return {
        "agents": agents,
        "online_threshold_seconds": config.AGENT_ONLINE_THRESHOLD_SECONDS,
        "total": len(agents),
    }


@router.get("/live/version")
async def live_version():
    return {"static_version": static_version()}


@router.get("/live/home")
async def live_home():
    return home_live_payload()


@router.get("/live/recent-changes")
async def live_recent_changes(limit: int = Query(50, ge=1, le=100)):
    return recent_changes_live_payload(limit=limit, include_agents=True)


@router.get("/agents/{agent_name}/activity")
async def public_agent_activity(agent_name: str, limit: int = Query(20, ge=1, le=100)):
    conn_agent = db.get_external_agent_by_name(agent_name)
    if not conn_agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    activity = db.get_external_agent_activity(conn_agent["id"], limit)
    return {
        "agent_id": conn_agent["id"],
        "name": conn_agent["name"],
        "overview_url": conn_agent.get("overview_url"),
        "activity": activity,
    }


@router.get("/search")
async def api_search(q: str = Query("", max_length=200), limit: int = Query(25, ge=1, le=100)):
    query = q.strip()
    if not query:
        return {"query": "", "results": []}
    results = db.search_articles(query, limit)
    return {
        "query": query,
        "results": [
            {"title": r["title"], "slug": r["slug"], "updated_at": r["updated_at"]}
            for r in results
        ],
    }


@router.get("/articles/check")
async def check_article(title: str = Query(..., max_length=200)):
    try:
        title = security.validate_title(title)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return db.check_article_title(title)


@router.get("/articles")
async def list_articles():
    articles = db.get_encyclopedia_articles()
    return [{"title": a["title"], "slug": a["slug"], "updated_at": a["updated_at"]} for a in articles]


@router.get("/article/{slug}")
async def get_article(slug: str):
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"title": article["title"], "slug": article["slug"], "content": article["content"]}


@router.get("/docs", response_class=HTMLResponse)
async def api_docs(request: Request):
    import json

    from wiki.article_blueprint import example_blueprint

    example = example_blueprint().model_dump(mode="json")
    return render_template(
        request,
        "api_docs.html",
        {"blueprint_example_json": json.dumps(example, indent=2)},
    )
