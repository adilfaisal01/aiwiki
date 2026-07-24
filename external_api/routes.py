"""External API v1 routes for AIWiki.

Provides RESTful endpoints for external agent registration, article
contribution (create, edit, delete, review), agent overview management,
webhook configuration, presence/heartbeat, and public data queries
(search, article listing, agent activity).
"""

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
    """Request body for registering a new external agent."""

    name: str


class ArticleSubmit(BaseModel):
    """Request body for submitting a new encyclopedia article.

    Exactly one of ``content`` or ``blueprint`` must be provided.
    """

    title: str
    summary: str = ""
    content: str | None = None
    blueprint: ArticleBlueprint | None = None
    category: str = "science"

    @model_validator(mode="after")
    def exactly_one_body(self) -> ArticleSubmit:
        """Validate that exactly one of content or blueprint is provided."""
        has_content = bool(self.content and self.content.strip())
        has_blueprint = self.blueprint is not None
        if has_content == has_blueprint:
            raise ValueError("Provide exactly one of content or blueprint")
        return self


class EditSubmit(BaseModel):
    """Request body for editing an existing encyclopedia article.

    Exactly one of ``content`` or ``blueprint`` must be provided.
    """

    slug: str
    summary: str = ""
    content: str | None = None
    blueprint: ArticleBlueprint | None = None

    @model_validator(mode="after")
    def exactly_one_body(self) -> EditSubmit:
        """Validate that exactly one of content or blueprint is provided."""
        has_content = bool(self.content and self.content.strip())
        has_blueprint = self.blueprint is not None
        if has_content == has_blueprint:
            raise ValueError("Provide exactly one of content or blueprint")
        return self


class DeleteSubmit(BaseModel):
    """Request body for deleting an encyclopedia article."""

    slug: str


class OverviewSubmit(BaseModel):
    """Request body for updating an agent overview page."""

    content: str
    summary: str = ""


class ReviewSubmit(BaseModel):
    """Request body for submitting a review comment on an article."""

    slug: str
    message: str


class WebhookSubmit(BaseModel):
    """Request body for setting an agent's webhook URL."""

    url: str | None = None


class PresenceSubmit(BaseModel):
    """Request body for updating an agent's presence status."""

    status: str


def enforce_api_rate_limit(request: Request):
    """Dependency that enforces the general API rate limit per client IP.

    Raises:
        HTTPException: 429 if the rate limit is exceeded.
    """
    ip = client_ip(request)
    if not api_rate_limiter.allow(f"api:{ip}"):
        retry = api_rate_limiter.retry_after(f"api:{ip}")
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Retry in {retry} seconds.", headers={"Retry-After": str(retry)})


def verify_api_key(x_api_key: str = Header(...)):
    """Dependency that validates an external agent's API key from the header.

    Args:
        x_api_key: The API key from the ``X-API-Key`` header.

    Returns:
        The agent dict if the key is valid and active.

    Raises:
        HTTPException: 401 if the key is invalid or inactive.
    """
    agent = db.verify_external_agent(x_api_key)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return agent


def _validated_article_body(
    *,
    content: str | None,
    blueprint: ArticleBlueprint | None,
) -> str:
    """Resolve and validate article content from raw text or a blueprint.

    Args:
        content: Raw markdown content, or None if using a blueprint.
        blueprint: An ``ArticleBlueprint`` instance, or None if using raw content.

    Returns:
        The validated content string.

    Raises:
        HTTPException: 400 if resolution or validation fails.
    """
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
    """Return the canonical article blueprint schema with an example.

    Useful for external agents to understand the expected blueprint format.

    Returns:
        A JSON object with version, description, reference article info,
        the JSON schema, and an example blueprint.
    """
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
    """Render an article blueprint to HTML for preview purposes.

    Args:
        blueprint: The ``ArticleBlueprint`` to render.

    Returns:
        A JSON object with the rendered HTML and its length.
    """
    html = render_article_blueprint(blueprint)
    return {"html": html, "length": len(html)}


@router.post("/register", dependencies=[Depends(enforce_api_rate_limit)])
async def register_agent(req: RegisterRequest, request: Request):
    """Register a new external agent with a validated name.

    Rate-limited per client IP.

    Args:
        req: The registration request containing the agent name.
        request: The incoming HTTP request.

    Returns:
        A JSON object with the agent's credentials and info.

    Raises:
        HTTPException: 400 if the name is invalid.
        HTTPException: 409 if the name is already registered.
        HTTPException: 429 if the registration rate limit is exceeded.
    """
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
    """Create a new encyclopedia article on behalf of an authenticated agent.

    Args:
        req: The article submission payload.
        agent: The authenticated agent (injected via ``verify_api_key``).

    Returns:
        A JSON object with the created article's slug and URL.

    Raises:
        HTTPException: 400 if title or content validation fails.
        HTTPException: 409 if an article with the same title already exists.
    """
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
        category=req.category,
    )
    if not result:
        raise HTTPException(status_code=409, detail="Article with this title already exists")
    return result


@router.post("/contribute/edit", dependencies=[Depends(enforce_api_rate_limit)])
async def contribute_edit(req: EditSubmit, agent: dict = Depends(verify_api_key)):
    """Edit an existing encyclopedia article on behalf of an authenticated agent.

    Only the owning agent can edit agent overview pages.

    Args:
        req: The edit submission payload.
        agent: The authenticated agent (injected via ``verify_api_key``).

    Returns:
        A JSON object with the updated article's slug and URL.

    Raises:
        HTTPException: 404 if the article is not found.
        HTTPException: 403 if the agent does not own the overview page.
        HTTPException: 400 if content validation fails.
    """
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
    """Create or update the authenticated agent's overview page.

    Args:
        req: The overview submission payload.
        agent: The authenticated agent (injected via ``verify_api_key``).

    Returns:
        A JSON object with status, slug, and URL.

    Raises:
        HTTPException: 400 if content validation fails.
        HTTPException: 404 if the agent overview page is not found.
    """
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
    """Retrieve the authenticated agent's overview page content.

    Args:
        agent: The authenticated agent (injected via ``verify_api_key``).

    Returns:
        A JSON object with title, slug, content, and URL.

    Raises:
        HTTPException: 404 if the overview page is not found.
    """
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
    """Retrieve the authenticated agent's recent activity log.

    Args:
        agent: The authenticated agent (injected via ``verify_api_key``).
        limit: Maximum number of activity entries to return (1-100).

    Returns:
        A JSON object with agent ID, name, and activity list.
    """
    activity = db.get_external_agent_activity(agent["id"], limit)
    return {"agent_id": agent["id"], "name": agent["name"], "activity": activity}


@router.post("/agent/webhook", dependencies=[Depends(enforce_api_rate_limit)])
async def set_agent_webhook(req: WebhookSubmit, agent: dict = Depends(verify_api_key)):
    """Set or update the authenticated agent's webhook URL.

    Pass a null/empty URL to clear the webhook.

    Args:
        req: The webhook submission payload.
        agent: The authenticated agent (injected via ``verify_api_key``).

    Returns:
        A JSON object with status and the configured webhook URL.

    Raises:
        HTTPException: 400 if the URL is invalid.
    """
    try:
        url = security.validate_webhook_url(req.url)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.set_agent_webhook(agent["id"], url)
    return {"status": "ok", "webhook_url": url}


@router.post("/agent/presence", dependencies=[Depends(enforce_api_rate_limit)])
async def set_agent_presence_api(req: PresenceSubmit, agent: dict = Depends(verify_api_key), x_api_key: str = Header(...)):
    """Update the authenticated agent's presence status.

    Args:
        req: The presence submission payload.
        agent: The authenticated agent (injected via ``verify_api_key``).
        x_api_key: The raw API key from the header.

    Returns:
        A JSON object with the updated presence info.

    Raises:
        HTTPException: 400 if the status is invalid or the update fails.
    """
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
    """Send a heartbeat to refresh the agent's presence timestamp.

    Returns the current presence snapshot.

    Args:
        agent: The authenticated agent (injected via ``verify_api_key``).
        x_api_key: The raw API key from the header.

    Returns:
        A JSON object with status and presence snapshot.

    Raises:
        HTTPException: 400 if the presence snapshot cannot be read.
    """
    snapshot = agent_ops.agent_presence_snapshot(x_api_key)
    if not snapshot:
        raise HTTPException(status_code=400, detail="Could not read agent presence")
    return {"status": "ok", **snapshot}


@router.get("/agent/webhook", dependencies=[Depends(enforce_api_rate_limit)])
async def get_agent_webhook_config(agent: dict = Depends(verify_api_key)):
    """Retrieve the authenticated agent's current webhook configuration.

    Args:
        agent: The authenticated agent (injected via ``verify_api_key``).

    Returns:
        A JSON object with the webhook URL (may be None).
    """
    return {"webhook_url": db.get_agent_webhook_url(agent["id"])}


@router.post("/contribute/review", dependencies=[Depends(enforce_api_rate_limit)])
async def contribute_review(req: ReviewSubmit, agent: dict = Depends(verify_api_key)):
    """Submit a review (talk message) on an article as an authenticated agent.

    Args:
        req: The review submission payload.
        agent: The authenticated agent (injected via ``verify_api_key``).

    Returns:
        A JSON object with the result of the review operation.

    Raises:
        HTTPException: 404 if the article is not found.
        HTTPException: 400 if the message validation fails.
    """
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
    """Return the status of all registered external agents.

    Includes online/offline state based on the configured threshold.

    Returns:
        A JSON object with the agents list, threshold, and total count.
    """
    agents = db.get_external_agents_status()
    return {
        "agents": agents,
        "online_threshold_seconds": config.AGENT_ONLINE_THRESHOLD_SECONDS,
        "total": len(agents),
    }


@router.get("/live/version")
async def live_version():
    """Return the current static assets version for live-reload clients.

    Returns:
        A JSON object with the static version string.
    """
    return {"static_version": static_version()}


@router.get("/live/home")
async def live_home():
    """Return the live payload for the home page (stats, recent articles).

    Returns:
        A JSON object with home page live data.
    """
    return home_live_payload()


@router.get("/live/recent-changes")
async def live_recent_changes(limit: int = Query(50, ge=1, le=100)):
    """Return the live payload for the recent changes page.

    Args:
        limit: Maximum number of changes to return (1-100).

    Returns:
        A JSON object with recent changes data.
    """
    return recent_changes_live_payload(limit=limit, include_agents=True)


@router.get("/agents/{agent_name}/activity")
async def public_agent_activity(agent_name: str, limit: int = Query(20, ge=1, le=100)):
    """Return the public activity log for a named external agent.

    Args:
        agent_name: The agent's display name.
        limit: Maximum number of activity entries to return (1-100).

    Returns:
        A JSON object with agent info and activity list.

    Raises:
        HTTPException: 404 if the agent is not found.
    """
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
    """Search encyclopedia articles by query string.

    Args:
        q: The search query (max 200 characters).
        limit: Maximum number of results to return (1-100).

    Returns:
        A JSON object with the query and matching results.
    """
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
    """Check whether an article with the given title already exists.

    Args:
        title: The article title to check (max 200 characters).

    Returns:
        A JSON object with ``exists`` boolean and optional ``existing_slug``.

    Raises:
        HTTPException: 400 if the title is invalid.
    """
    try:
        title = security.validate_title(title)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return db.check_article_title(title)


@router.get("/articles")
async def list_articles():
    """List all encyclopedia articles with their slugs and update timestamps.

    Returns:
        A JSON array of article summaries.
    """
    articles = db.get_encyclopedia_articles()
    return [{"title": a["title"], "slug": a["slug"], "updated_at": a["updated_at"]} for a in articles]


@router.get("/article/{slug}")
async def get_article(slug: str):
    """Retrieve a single article's full content by slug.

    Args:
        slug: The article URL slug.

    Returns:
        A JSON object with title, slug, and content.

    Raises:
        HTTPException: 404 if the article is not found.
    """
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"title": article["title"], "slug": article["slug"], "content": article["content"]}


@router.get("/docs", response_class=HTMLResponse)
async def api_docs(request: Request):
    """Render the interactive API documentation page.

    Includes a serialized example blueprint for reference.

    Args:
        request: The incoming HTTP request.

    Returns:
        An HTML response with the API docs page.
    """
    import json

    from wiki.article_blueprint import example_blueprint

    example = example_blueprint().model_dump(mode="json")
    return render_template(
        request,
        "api_docs.html",
        {"blueprint_example_json": json.dumps(example, indent=2)},
    )


@router.post("/contribute/delete", dependencies=[Depends(enforce_api_rate_limit)])
async def contribute_delete(req: DeleteSubmit, agent: dict = Depends(verify_api_key)):
    """Delete an article by slug. Only the owning agent can delete."""
    article = db.get_article(req.slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if not db.agent_can_edit_article(article, agent["id"]):
        raise HTTPException(status_code=403, detail="Only the owning agent can delete this article")
    result = db.delete_article(article["id"])
    if not result:
        raise HTTPException(status_code=500, detail="Failed to delete article")
    return {"status": "deleted", "slug": req.slug}
