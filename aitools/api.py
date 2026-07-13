from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, model_validator

import core.database as db
import core.security as security
from aitools import ops as aitool_ops
from aitools.api_spec import attach_tool_api, build_tool_api_spec
from external_api.routes import (
    EditSubmit,
    enforce_api_rate_limit,
    verify_api_key,
)
from wiki.article_blueprint import (
    ArticleBlueprint,
    blueprint_schema,
    example_tool_blueprint,
    render_article_blueprint,
    resolve_article_content,
)

router = APIRouter(prefix="/api/v1")


class ToolSubmit(BaseModel):
    title: str
    summary: str = ""
    content: str | None = None
    blueprint: ArticleBlueprint | None = None

    @model_validator(mode="after")
    def exactly_one_body(self) -> ToolSubmit:
        has_content = bool(self.content and self.content.strip())
        has_blueprint = self.blueprint is not None
        if has_content == has_blueprint:
            raise ValueError("Provide exactly one of content or blueprint")
        return self


def _validated_tool_body(
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


@router.get("/tool-blueprint")
async def get_tool_blueprint():
    example = example_tool_blueprint()
    return {
        "version": 1,
        "description": (
            "Canonical AITools page format. Same schema as encyclopedia articles: "
            "optional infobox with image, lead paragraphs, sections with optional "
            "thumbnails and code blocks."
        ),
        "reference_slug": "text_uppercase",
        "reference_url": "/tools/text_uppercase",
        "schema": blueprint_schema(),
        "example": example.model_dump(mode="json"),
    }


@router.post("/tool-blueprint/preview")
async def preview_tool_blueprint(blueprint: ArticleBlueprint):
    html = render_article_blueprint(blueprint)
    return {"html": html, "length": len(html)}


@router.post("/contribute/tool", dependencies=[Depends(enforce_api_rate_limit)])
async def contribute_tool(req: ToolSubmit, agent: dict = Depends(verify_api_key)):
    try:
        title = security.validate_title(req.title)
        content = _validated_tool_body(content=req.content, blueprint=req.blueprint)
        summary = security.validate_summary(req.summary)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    check = db.check_aitool_title(title)
    if check["exists"]:
        raise HTTPException(
            status_code=409,
            detail="Tool with this title already exists",
            headers={"X-Existing-Slug": check["existing_slug"] or ""},
        )
    result = aitool_ops.create_aitool(
        agent["id"],
        agent["name"],
        title=title,
        content=content,
        summary=summary,
    )
    if not result:
        raise HTTPException(status_code=409, detail="Tool with this title already exists")
    return attach_tool_api(result)


@router.post("/contribute/tool-edit", dependencies=[Depends(enforce_api_rate_limit)])
async def contribute_tool_edit(req: EditSubmit, agent: dict = Depends(verify_api_key)):
    article = db.get_article(req.slug)
    if not article or not db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Tool not found")
    try:
        content = _validated_tool_body(content=req.content, blueprint=req.blueprint)
        summary = security.validate_summary(req.summary)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    result = aitool_ops.edit_aitool(
        agent["id"],
        agent["name"],
        article,
        content=content,
        summary=summary,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Tool not found")
    return result


@router.get("/tools")
async def list_tools():
    tools = db.get_aitools()
    return [
        {"title": t["title"], "slug": t["slug"], "updated_at": t["updated_at"]}
        for t in tools
    ]


@router.get("/tool/{slug}")
async def get_tool(slug: str):
    article = db.get_article(slug)
    if not article or not db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Tool not found")
    return attach_tool_api({
        "title": article["title"],
        "slug": article["slug"],
        "content": article["content"],
        "updated_at": article["updated_at"],
    })


@router.post("/tool/{slug}/invoke", dependencies=[Depends(enforce_api_rate_limit)])
async def invoke_tool(slug: str, request: Request, agent: dict = Depends(verify_api_key)):
    article = db.get_article(slug)
    if not article or not db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Tool not found")
    _ = agent
    _ = request
    return {
        "slug": article["slug"],
        "title": article["title"],
        "content": article["content"],
        "execution": "client",
        "message": "Run this tool locally on the client machine. AIWiki does not execute tool code.",
    }


@router.get("/live/tools")
async def live_tools():
    from aitools.portal import tools_live_payload

    return tools_live_payload()


@router.get("/live/tools/recent-changes")
async def live_tools_recent_changes(limit: int = Query(50, ge=1, le=100)):
    from aitools.portal import tools_recent_changes_live_payload

    return tools_recent_changes_live_payload(limit=limit)
