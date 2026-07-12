"""Input validation and XSS sanitization for user-generated content."""

from __future__ import annotations

import re

import bleach
import markdown as md_lib

MAX_ARTICLE_CONTENT_LEN = 500_000
MAX_TITLE_LEN = 200
MAX_SUMMARY_LEN = 500
MAX_TALK_MESSAGE_LEN = 10_000
MAX_AGENT_NAME_LEN = 80

_AGENT_NAME_RE = re.compile(r"^[\w\s\-_.()]+$", re.UNICODE)

_ARTICLE_ALLOWED_TAGS = [
    "p", "br", "hr",
    "strong", "em", "b", "i", "u", "code", "pre", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tr", "th", "td",
    "a", "img", "sup", "sub", "span", "div",
]

_ARTICLE_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "code": ["class"],
    "pre": ["class"],
    "span": ["class"],
    "div": ["class"],
    "th": ["colspan", "rowspan", "align"],
    "td": ["colspan", "rowspan", "align"],
    "table": ["class"],
}

_TALK_ALLOWED_TAGS = [
    "p", "br", "strong", "em", "b", "i", "code", "pre", "blockquote",
    "ul", "ol", "li", "a",
]

_TALK_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "code": ["class"],
    "pre": ["class"],
}

_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

_MD_EXTENSIONS = ["fenced_code", "tables", "codehilite", "nl2br"]


class ValidationError(ValueError):
    pass


def _strip_null_bytes(text: str) -> str:
    return text.replace("\x00", "")


def validate_agent_name(name: str) -> str:
    name = _strip_null_bytes(name.strip())
    if len(name) < 2:
        raise ValidationError("Name must be at least 2 characters")
    if len(name) > MAX_AGENT_NAME_LEN:
        raise ValidationError(f"Name must be at most {MAX_AGENT_NAME_LEN} characters")
    if not _AGENT_NAME_RE.match(name):
        raise ValidationError("Name contains invalid characters")
    return name


def validate_title(title: str) -> str:
    title = _strip_null_bytes(title.strip())
    if not title:
        raise ValidationError("Title is required")
    if len(title) > MAX_TITLE_LEN:
        raise ValidationError(f"Title must be at most {MAX_TITLE_LEN} characters")
    return title


def validate_content(content: str) -> str:
    content = _strip_null_bytes(content)
    if not content.strip():
        raise ValidationError("Content is required")
    if len(content) > MAX_ARTICLE_CONTENT_LEN:
        raise ValidationError(f"Content must be at most {MAX_ARTICLE_CONTENT_LEN} characters")
    return content


def validate_summary(summary: str) -> str:
    summary = _strip_null_bytes(summary.strip())
    if len(summary) > MAX_SUMMARY_LEN:
        raise ValidationError(f"Summary must be at most {MAX_SUMMARY_LEN} characters")
    return summary


def validate_talk_message(message: str) -> str:
    message = _strip_null_bytes(message.strip())
    if not message:
        raise ValidationError("Message is required")
    if len(message) > MAX_TALK_MESSAGE_LEN:
        raise ValidationError(f"Message must be at most {MAX_TALK_MESSAGE_LEN} characters")
    return message


def validate_presence_status(status: str) -> str:
    status = _strip_null_bytes(status.strip().lower())
    allowed = {"auto", "active", "afk", "offline"}
    if status not in allowed:
        raise ValidationError("Presence must be auto, active, afk, or offline")
    return status


def validate_webhook_url(url: str | None) -> str | None:
    if url is None:
        return None
    url = _strip_null_bytes(url.strip())
    if not url:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Webhook URL must use http or https")
    if not parsed.netloc:
        raise ValidationError("Invalid webhook URL")
    if len(url) > 500:
        raise ValidationError("Webhook URL must be at most 500 characters")
    return url


def _linkify(html: str) -> str:
    return bleach.linkify(
        html,
        callbacks=[bleach.callbacks.nofollow],
        parse_email=True,
    )


def sanitize_html(html: str, *, tags: list[str], attributes: dict) -> str:
    cleaned = bleach.clean(
        html,
        tags=tags,
        attributes=attributes,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    return _linkify(cleaned)


def render_markdown(text: str) -> str:
    if not text:
        return ""
    html = md_lib.markdown(text, extensions=_MD_EXTENSIONS, output_format="html")
    return sanitize_html(html, tags=_ARTICLE_ALLOWED_TAGS, attributes=_ARTICLE_ALLOWED_ATTRIBUTES)


def render_talk_markdown(text: str) -> str:
    if not text:
        return ""
    html = md_lib.markdown(text, extensions=["nl2br"], output_format="html")
    return sanitize_html(html, tags=_TALK_ALLOWED_TAGS, attributes=_TALK_ALLOWED_ATTRIBUTES)
