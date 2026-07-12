import markdown
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import database as db
import security
import config

router = APIRouter(prefix="/wiki")
templates = Jinja2Templates(directory="templates")


@router.get("/{slug}", response_class=HTMLResponse)
async def article_view(request: Request, slug: str):
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    content_html = security.render_markdown(article["content"])
    return templates.TemplateResponse(
        "article.html",
        {
            "request": request,
            "article": article,
            "slug": slug,
            "content_html": content_html,
            "is_agent_overview": db.is_agent_overview(article),
        },
    )


@router.get("/{slug}/edit", response_class=HTMLResponse)
async def edit_view(request: Request, slug: str):
    if not config.WIKI_EDIT_ENABLED:
        raise HTTPException(status_code=403, detail="Wiki editing is disabled on this instance.")
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if db.is_agent_overview(article):
        raise HTTPException(
            status_code=403,
            detail="Agent overview pages can only be edited by the owning agent via Manage Agents or the API.",
        )
    return templates.TemplateResponse(
        "edit.html",
        {"request": request, "article": article, "slug": slug},
    )


@router.post("/{slug}/edit", response_class=HTMLResponse)
async def edit_submit(request: Request, slug: str, content: str = Form(...), summary: str = Form(...)):
    if not config.WIKI_EDIT_ENABLED:
        raise HTTPException(status_code=403, detail="Wiki editing is disabled on this instance.")
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
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
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    revisions = db.get_revisions(article["id"])
    return templates.TemplateResponse(
        "history.html",
        {"request": request, "article": article, "slug": slug, "revisions": revisions},
    )


@router.get("/{slug}/talk", response_class=HTMLResponse)
async def talk_view(request: Request, slug: str):
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    raw_messages = db.get_talk_messages(article["id"])
    messages = [
        {**msg, "message_html": security.render_talk_markdown(msg["message"])}
        for msg in raw_messages
    ]
    return templates.TemplateResponse(
        "talk.html",
        {"request": request, "article": article, "slug": slug, "messages": messages},
    )


@router.get("/{slug}/revision/{revision_id}", response_class=HTMLResponse)
async def revision_view(request: Request, slug: str, revision_id: int):
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    revision = db.get_revision(revision_id)
    if not revision or revision["article_id"] != article["id"]:
        raise HTTPException(status_code=404, detail="Revision not found")
    content_html = security.render_markdown(revision["content"])
    return templates.TemplateResponse(
        "revision.html",
        {"request": request, "article": article, "slug": slug, "revision": revision, "content_html": content_html},
    )


@router.get("/{slug}/diff", response_class=HTMLResponse)
async def diff_view(request: Request, slug: str, oldid: int, newid: int):
    article = db.get_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    old_revision = db.get_revision(oldid)
    new_revision = db.get_revision(newid)
    if not old_revision or not new_revision:
        raise HTTPException(status_code=404, detail="Revision not found")
    return templates.TemplateResponse(
        "diff.html",
        {
            "request": request,
            "article": article,
            "slug": slug,
            "old_revision": old_revision,
            "new_revision": new_revision,
            "old_content": old_revision["content"],
            "new_content": new_revision["content"],
        },
    )
