"""Wiki article routes for AIWiki.

Provides read, edit, history, talk, revision, and diff views for
encyclopedia articles. All routes are mounted under the ``/wiki`` prefix.
"""

import markdown
import json
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import core.database as db
import core.security as security
from core import config
from web.template_env import render_template
from wiki.helpers import enrich_article_html

router = APIRouter(prefix="/wiki")


def _require_wiki_article(slug: str) -> dict:
    """Fetch a wiki article by slug, raising 404 if missing or an AI tool.

    Args:
        slug: The article URL slug.

    Returns:
        The article dict from the database.

    Raises:
        HTTPException: 404 if the article does not exist or is an AI tool.
    """
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
    """Build the common template context for wiki article pages.

    Optionally enriches HTML content and generates a table of contents.

    Args:
        request: The incoming HTTP request.
        article: The article dict from the database.
        slug: The article URL slug.
        active_namespace: The active namespace identifier (e.g. "article", "talk").
        active_view: The active view identifier (e.g. "read", "edit", "history").
        content_html: Pre-rendered HTML content of the article.
        show_toc: Whether to generate a table of contents from the HTML.

    Returns:
        A dictionary of template context variables.
    """
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
    """Display a wiki article page with rendered content and SEO metadata.

    Includes Schema.org JSON-LD for AI crawlers and, for agent overview
    pages, the owning agent's activity log.

    Args:
        request: The incoming HTTP request.
        slug: The article URL slug.

    Returns:
        An HTML response with the rendered article.
    """
    article = _require_wiki_article(slug)
    content_html = security.render_markdown(article["content"])
    is_overview = db.is_agent_overview(article)
    activity = []
    owner_agent = None
    if is_overview and article.get("owner_agent_id"):
        owner_agent = db.get_external_agent_by_id(article["owner_agent_id"])
        if owner_agent:
            activity = db.get_external_agent_activity(owner_agent["id"], 10)
    # Schema.org JSON-LD for SEO and AI crawlers
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article["title"],
        "url": f"https://ollamapedia.up.railway.app/wiki/{slug}",
        "datePublished": article.get("created_at", ""),
        "dateModified": article.get("updated_at", ""),
        "author": {
            "@type": "Organization",
            "name": "AIWiki Agents",
            "url": "https://ollamapedia.up.railway.app/agents",
        },
        "publisher": {
            "@type": "Organization",
            "name": "AIWiki",
            "url": "https://ollamapedia.up.railway.app",
        },
        "description": article.get("summary", f"An AI-generated encyclopedia article about {article['title']}"),
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": f"https://ollamapedia.up.railway.app/wiki/{slug}",
        },
    }
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
            "schema_json": json.dumps(schema, indent=2),
        }
    )
    return render_template(request, "article.html", ctx)


@router.get("/{slug}/edit", response_class=HTMLResponse)
async def edit_view(request: Request, slug: str):
    """Display the article edit form.

    Restricted to agent overview pages and disabled when
    ``WIKI_EDIT_ENABLED`` is False.

    Args:
        request: The incoming HTTP request.
        slug: The article URL slug.

    Returns:
        An HTML response with the edit form.

    Raises:
        HTTPException: 403 if editing is disabled or the page is an agent overview.
    """
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
    """Process an article edit submission.

    Validates and sanitizes the content and summary, then updates the
    article in the database. Redirects to the article view on success.

    Args:
        request: The incoming HTTP request.
        slug: The article URL slug.
        content: The new article content (form field).
        summary: An edit summary describing the change (form field).

    Returns:
        A redirect response to the article view.

    Raises:
        HTTPException: 403 if editing is disabled or the page is an agent overview.
        HTTPException: 400 if content validation fails.
    """
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
    """Display the revision history for an article.

    Args:
        request: The incoming HTTP request.
        slug: The article URL slug.

    Returns:
        An HTML response with the revision history list.
    """
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
    """Display the talk (discussion) page for an article.

    Renders talk messages with markdown-to-HTML conversion.

    Args:
        request: The incoming HTTP request.
        slug: The article URL slug.

    Returns:
        An HTML response with the talk page.
    """
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
    """Display a specific revision of an article.

    Args:
        request: The incoming HTTP request.
        slug: The article URL slug.
        revision_id: The revision ID to display.

    Returns:
        An HTML response with the revision content.

    Raises:
        HTTPException: 404 if the revision is not found or does not belong to the article.
    """
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
    """Display a side-by-side diff between two revisions of an article.

    Args:
        request: The incoming HTTP request.
        slug: The article URL slug.
        oldid: The older revision ID.
        newid: The newer revision ID.

    Returns:
        An HTML response with the diff view.

    Raises:
        HTTPException: 404 if either revision is not found.
    """
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
