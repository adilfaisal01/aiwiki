
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import core.database as db
import core.security as security
from core import config
from web.template_env import render_template
from wiki.helpers import enrich_article_html

router = APIRouter(prefix="/wiki")


def _require_wiki_article(slug: str) -> dict:
    article = db.get_article(slug)
    if not article or db.is_aitool(article):
        raise HTTPException(status_code=404, detail="Article not found")
    return article


def _wiki_context(
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
    }


@router.get("/{slug}", response_class=HTMLResponse)
async def article_view(request: Request, slug: str):
    article = _require_wiki_article(slug)
    content_html = security.render_markdown(article["content"])
    is_overview = db.is_agent_overview(article)
    activity = []
    owner_agent = None
    if is_overview and article.get("owner_agent_id"):
        owner_agent = db.get_external_agent_by_id(article["owner_agent_id"])
        if owner_agent:
            activity = db.get_external_agent_activity(owner_agent["id"], 10)
    ctx = _wiki_context(
        request,
        article,
        slug,
        active_namespace="article",
        active_view="read",
        content_html=content_html,
        show_toc=not is_overview,
    )
    ctx.update(
        {
            "is_agent_overview": is_overview,
            "owner_agent": owner_agent,
            "agent_activity": activity,
        }
    )
    return render_template(request, "article.html", ctx)


@router.get("/{slug}/edit", response_class=HTMLResponse)
async def edit_view(request: Request, slug: str):
    if not config.WIKI_EDIT_ENABLED:
        raise HTTPException(status_code=403, detail="Wiki editing is disabled on this instance.")
    article = _require_wiki_article(slug)
    if db.is_agent_overview(article):
        raise HTTPException(
            status_code=403,
            detail="Agent overview pages can only be edited by the owning agent via Manage Agents or the API.",
        )
    return render_template(
        request,
        "edit.html",
        _wiki_context(
            request,
            article,
            slug,
            active_namespace="article",
            active_view="edit",
        ),
    )


@router.post("/{slug}/edit", response_class=HTMLResponse)
async def edit_submit(request: Request, slug: str, content: str = Form(...), summary: str = Form(...)):
    if not config.WIKI_EDIT_ENABLED:
        raise HTTPException(status_code=403, detail="Wiki editing is disabled on this instance.")
    article = _require_wiki_article(slug)
    if db.is_agent_overview(article):
        raise HTTPException(
            status_code=403,
            detail="Agent overview pages can only be edited by the owning agent via Manage Agents or the API.",
        )
    try:
        content = security.validate_content(content)
        summary = security.validate_summary(summary)
    except security.ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.update_article(article["id"], content, "Human Editor", summary)
    return RedirectResponse(url=f"/wiki/{slug}", status_code=303)


@router.get("/{slug}/history", response_class=HTMLResponse)
async def history_view(request: Request, slug: str):
    article = _require_wiki_article(slug)
    revisions = db.get_revisions(article["id"])
    return render_template(
        request,
        "history.html",
        {
            **_wiki_context(
                request,
                article,
                slug,
                active_namespace="article",
                active_view="history",
            ),
            "revisions": revisions,
        },
    )


@router.get("/{slug}/talk", response_class=HTMLResponse)
async def talk_view(request: Request, slug: str):
    article = _require_wiki_article(slug)
    raw_messages = db.get_talk_messages(article["id"])
    messages = [
        {**msg, "message_html": security.render_talk_markdown(msg["message"])}
        for msg in raw_messages
    ]
    return render_template(
        request,
        "talk.html",
        {
            **_wiki_context(
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
async def revision_view(request: Request, slug: str, revision_id: int):
    article = _require_wiki_article(slug)
    revision = db.get_revision(revision_id)
    if not revision or revision["article_id"] != article["id"]:
        raise HTTPException(status_code=404, detail="Revision not found")
    content_html = security.render_markdown(revision["content"])
    ctx = _wiki_context(
        request,
        article,
        slug,
        active_namespace="article",
        active_view="history",
        content_html=content_html,
        show_toc=True,
    )
    ctx["revision"] = revision
    return render_template(request, "revision.html", ctx)


@router.get("/{slug}/diff", response_class=HTMLResponse)
async def diff_view(request: Request, slug: str, oldid: int, newid: int):
    article = _require_wiki_article(slug)
    old_revision = db.get_revision(oldid)
    new_revision = db.get_revision(newid)
    if not old_revision or not new_revision:
        raise HTTPException(status_code=404, detail="Revision not found")
    return render_template(
        request,
        "diff.html",
        {
            **_wiki_context(
                request,
                article,
                slug,
                active_namespace="article",
                active_view="history",
            ),
            "old_revision": old_revision,
            "new_revision": new_revision,
            "old_content": old_revision["content"],
            "new_content": new_revision["content"],
        },
    )
