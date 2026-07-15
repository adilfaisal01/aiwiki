from __future__ import annotations

import random

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import core.database as db
import core.security as security
from core import config
from aitools.api_spec import build_tool_api_spec
from aitools.tool_spec import tool_execution_mode
from aitools.portal import tools_portal_data
from web.template_env import render_template
from wiki.helpers import enrich_article_html

router = APIRouter(prefix="/tools")


def _tool_context(
    request: Request,
    article: dict,
    slug: str,
    *,
    active_namespace: str,
    active_view: str,
    content_html: str = "",
    show_toc: bool = False,
) -> dict:
    enriched_html = content_html
    toc = []
    if content_html and show_toc:
        enriched_html, toc = enrich_article_html(content_html)
    return {
        "request": request,
        "article": article,
        "slug": slug,
        "content_html": enriched_html,
        "toc": toc,
        "show_toc": show_toc and bool(toc),
        "active_namespace": active_namespace,
        "active_view": active_view,
        "page_base": "/tools",
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def tools_index(request: Request):
    try:
        portal = tools_portal_data(featured_limit=20, recent_limit=8)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not load tools") from None
    return render_template(
        request,
        "tools_index.html",
        {
            "tools": portal["tools"],
            "recent_changes": portal["recent_changes"],
            "tool_count": portal["tool_count"],
            "tool_of_day": portal["tool_of_day"],
        },
    )


@router.get("/recent-changes", response_class=HTMLResponse)
async def tools_recent_changes(request: Request):
    try:
        changes = db.get_aitool_recent_changes(50)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not load recent changes") from None
    return render_template(request, "tools_recent_changes.html", {"changes": changes})


@router.get("/search", response_class=HTMLResponse)
async def tools_search_page(request: Request, q: str = Query("", max_length=200)):
    query = q.strip()
    results = db.search_aitools(query, 30) if query else []
    return render_template(
        request,
        "tools_search.html",
        {"query": query, "results": results},
    )


@router.get("/random")
async def random_tool():
    tools = db.get_aitools()
    if not tools:
        return RedirectResponse(url="/tools", status_code=303)
    tool = random.choice(tools)
    return RedirectResponse(url=f"/tools/{tool['slug']}", status_code=303)


@router.get("/{slug}", response_class=HTMLResponse)
async def tool_view(request: Request, slug: str):
    article = db.get_article(slug)
    if not article or not db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Tool not found")
    content_html = security.render_markdown(article["content"])
    ctx = _tool_context(
        request,
        article,
        slug,
        active_namespace="tool",
        active_view="read",
        content_html=content_html,
        show_toc=True,
    )
    ctx["tool_api"] = build_tool_api_spec(article, public_base_url=str(request.base_url).rstrip("/"))
    ctx["tool_server_execution"] = tool_execution_mode(article) == "server"
    return render_template(request, "tool.html", ctx)


@router.get("/{slug}/edit", response_class=HTMLResponse)
async def tool_edit_view(request: Request, slug: str):
    if not config.WIKI_EDIT_ENABLED:
        raise HTTPException(status_code=403, detail="Editing is disabled on this instance.")
    article = db.get_article(slug)
    if not article or not db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Tool not found")
    return render_template(
        request,
        "tool_edit.html",
        _tool_context(
            request,
            article,
            slug,
            active_namespace="tool",
            active_view="edit",
        ),
    )


@router.post("/{slug}/edit", response_class=HTMLResponse)
async def tool_edit_submit(request: Request, slug: str, content: str = Form(...), summary: str = Form(...)):
    if not config.WIKI_EDIT_ENABLED:
        raise HTTPException(status_code=403, detail="Editing is disabled on this instance.")
    article = db.get_article(slug)
    if not article or not db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Tool not found")
    try:
        content = security.validate_content(content)
        summary = security.validate_summary(summary)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.update_article(article["id"], content, "Human Editor", summary)
    return RedirectResponse(url=f"/tools/{slug}", status_code=303)


@router.get("/{slug}/history", response_class=HTMLResponse)
async def tool_history_view(request: Request, slug: str):
    article = db.get_article(slug)
    if not article or not db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Tool not found")
    revisions = db.get_revisions(article["id"])
    return render_template(
        request,
        "tool_history.html",
        {
            **_tool_context(
                request,
                article,
                slug,
                active_namespace="tool",
                active_view="history",
            ),
            "revisions": revisions,
        },
    )


@router.get("/{slug}/talk", response_class=HTMLResponse)
async def tool_talk_view(request: Request, slug: str):
    article = db.get_article(slug)
    if not article or not db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Tool not found")
    raw_messages = db.get_talk_messages(article["id"])
    messages = [
        {**msg, "message_html": security.render_talk_markdown(msg["message"])}
        for msg in raw_messages
    ]
    return render_template(
        request,
        "tool_talk.html",
        {
            **_tool_context(
                request,
                article,
                slug,
                active_namespace="talk",
                active_view="read",
            ),
            "messages": messages,
        },
    )


@router.get("/{slug}/revision/{revision_id}", response_class=HTMLResponse)
async def tool_revision_view(request: Request, slug: str, revision_id: int):
    article = db.get_article(slug)
    if not article or not db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Tool not found")
    revision = db.get_revision(revision_id)
    if not revision or revision["article_id"] != article["id"]:
        raise HTTPException(status_code=404, detail="Revision not found")
    content_html = security.render_markdown(revision["content"])
    ctx = _tool_context(
        request,
        article,
        slug,
        active_namespace="tool",
        active_view="history",
        content_html=content_html,
        show_toc=True,
    )
    ctx["revision"] = revision
    return render_template(request, "tool_revision.html", ctx)


@router.get("/{slug}/diff", response_class=HTMLResponse)
async def tool_diff_view(request: Request, slug: str, oldid: int, newid: int):
    article = db.get_article(slug)
    if not article or not db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Tool not found")
    old_revision = db.get_revision(oldid)
    new_revision = db.get_revision(newid)
    if not old_revision or not new_revision:
        raise HTTPException(status_code=404, detail="Revision not found")
    return render_template(
        request,
        "tool_diff.html",
        {
            **_tool_context(
                request,
                article,
                slug,
                active_namespace="tool",
                active_view="history",
            ),
            "old_revision": old_revision,
            "new_revision": new_revision,
            "old_content": old_revision["content"],
            "new_content": new_revision["content"],
        },
    )
