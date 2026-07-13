"""Builtin server tool handlers referenced by article tool specs."""

from __future__ import annotations

import html
import re
from typing import Any, Awaitable, Callable

import httpx

_BUILTIN_HANDLERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]] = {}

_DDG_RESULT_RE = re.compile(
    r'class="result__a"\s+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'.*?class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


def register_builtin_handler(
    handler_id: str,
) -> Callable[
    [Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]],
    Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]],
]:
    def decorator(
        fn: Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]:
        _BUILTIN_HANDLERS[handler_id] = fn
        return fn

    return decorator


def has_builtin_handler(handler_id: str) -> bool:
    return handler_id in _BUILTIN_HANDLERS


async def execute_builtin_handler(
    handler_id: str,
    body: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    handler = _BUILTIN_HANDLERS.get(handler_id)
    if not handler:
        raise KeyError(f"Unknown server handler: {handler_id}")
    return await handler(body, config or {})


def _strip_tags(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text)).strip()


def _parse_ddg_html(page: str, limit: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for match in _DDG_RESULT_RE.finditer(page):
        title = _strip_tags(match.group("title"))
        snippet = _strip_tags(match.group("snippet"))
        url = html.unescape(match.group("url").strip())
        if not title or not url:
            continue
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


async def _ddg_instant_answer(query: str, limit: int) -> list[dict[str, str]]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
            },
        )
        response.raise_for_status()
        payload = response.json()

    results: list[dict[str, str]] = []
    abstract = (payload.get("AbstractText") or "").strip()
    abstract_url = (payload.get("AbstractURL") or "").strip()
    if abstract:
        heading = (payload.get("Heading") or query).strip()
        results.append({
            "title": heading,
            "url": abstract_url or "https://duckduckgo.com/",
            "snippet": abstract,
        })

    for topic in payload.get("RelatedTopics") or []:
        if len(results) >= limit:
            break
        if not isinstance(topic, dict):
            continue
        if "Topics" in topic:
            for nested in topic.get("Topics") or []:
                if len(results) >= limit:
                    break
                if not isinstance(nested, dict):
                    continue
                text = (nested.get("Text") or "").strip()
                if not text:
                    continue
                url = (nested.get("FirstURL") or "").strip()
                title, _, snippet = text.partition(" - ")
                results.append({
                    "title": title.strip() or text,
                    "url": url or "https://duckduckgo.com/",
                    "snippet": snippet.strip() or text,
                })
            continue
        text = (topic.get("Text") or "").strip()
        if not text:
            continue
        url = (topic.get("FirstURL") or "").strip()
        title, _, snippet = text.partition(" - ")
        results.append({
            "title": title.strip() or text,
            "url": url or "https://duckduckgo.com/",
            "snippet": snippet.strip() or text,
        })
    return results[:limit]


async def search_web(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    limit = max(1, min(limit, 10))
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "b": "", "kl": ""},
            headers={
                "User-Agent": "AIWikiWebSearchTool/1.0",
                "Accept": "text/html",
            },
        )
        response.raise_for_status()
        results = _parse_ddg_html(response.text, limit)

    if results:
        return results
    return await _ddg_instant_answer(query, limit)


@register_builtin_handler("web_search")
async def run_web_search(
    body: dict[str, Any],
    _config: dict[str, Any],
) -> dict[str, Any]:
    query = str(body.get("query") or "").strip()
    if len(query) < 2:
        raise ValueError("query must be at least 2 characters")
    try:
        limit = int(body.get("limit", 5))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    limit = max(1, min(limit, 10))
    results = await search_web(query, limit=limit)
    return {
        "query": query,
        "count": len(results),
        "results": results,
    }
