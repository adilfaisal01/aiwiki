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
    "figure": ["class"],
    "figcaption": ["class"],
    "th": ["colspan", "rowspan", "align", "class"],
    "td": ["colspan", "rowspan", "align", "class"],
    "table": ["class"],
    "h2": ["id"],
    "h3": ["id"],
    "sup": ["id", "class"],
    "li": ["id"],
    "ol": ["class"],
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
_MD_EXTENSION_CONFIGS = {
    "codehilite": {
        "css_class": "codehilite",
        "guess_lang": True,
        "linenos": False,
    },
}


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

    # SSRF protection — block private/reserved IPs
    from core.webhooks import validate_webhook_url as ssrf_check
    valid, msg = ssrf_check(url)
    if not valid:
        raise ValidationError(msg)

    return url


def validate_avatar_url(url: str | None) -> str | None:
    if url is None:
        return None
    url = _strip_null_bytes(url.strip())
    if not url:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Avatar URL must use http or https")
    if not parsed.netloc:
        raise ValidationError("Invalid avatar URL")
    if len(url) > 500:
        raise ValidationError("Avatar URL must be at most 500 characters")
    return url


_ACCOUNT_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_email(email: str) -> str:
    email = _strip_null_bytes(email.strip().lower())
    if not email:
        raise ValidationError("Email is required")
    if len(email) > 254:
        raise ValidationError("Email must be at most 254 characters")
    if not _EMAIL_RE.match(email):
        raise ValidationError("Invalid email address")
    return email


def validate_password(password: str) -> str:
    password = _strip_null_bytes(password)
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters")
    if len(password) > 128:
        raise ValidationError("Password must be at most 128 characters")
    return password


def validate_account_id(account_id: str) -> str:
    account_id = _strip_null_bytes(account_id.strip())
    if not _ACCOUNT_ID_RE.match(account_id):
        raise ValidationError("Invalid account ID")
    return account_id.lower()


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


def sanitize_article_html(html: str) -> str:
    return sanitize_html(html, tags=_ARTICLE_ALLOWED_TAGS, attributes=_ARTICLE_ALLOWED_ATTRIBUTES)


def _render_wikilinks(text: str) -> str:
    """Convert [[Topic]] to markdown links before markdown processing."""
    import re
    def _replace(match):
        topic = match.group(1).strip()
        slug = re.sub(r'[^a-z0-9]+', '_', topic.lower()).strip('_')
        return f"[{topic}](/wiki/{slug})"
    return re.sub(r'\[\[([^\]]+)\]\]', _replace, text)


_MATH_PLACEHOLDER = "\x00MATH\x00"


def _protect_math(text: str) -> tuple[str, list[str]]:
    """Protect LaTeX math expressions from markdown processing.

    Replaces math delimiters with placeholders so underscores and
    other markdown-significant characters inside math are preserved.
    """
    placeholders = []
    def _replace(match):
        placeholder = f"{_MATH_PLACEHOLDER}{len(placeholders)}{_MATH_PLACEHOLDER}"
        placeholders.append(match.group(0))
        return placeholder
    # Protect display math $$...$$ and \[...\] first (greedy)
    text = re.sub(r'\$\$(.+?)\$\$', _replace, text, flags=re.DOTALL)
    text = re.sub(r'\\\[(.+?)\\\]', _replace, text, flags=re.DOTALL)
    # Then protect inline math $...$ and \(...\)
    text = re.sub(r'\$(.+?)\$', _replace, text)
    text = re.sub(r'\\\((.+?)\\\)', _replace, text)
    return text, placeholders


def _restore_math(html: str, placeholders: list[str]) -> str:
    """Restore protected math expressions after markdown processing."""
    for i, expr in enumerate(placeholders):
        placeholder = f"{_MATH_PLACEHOLDER}{i}{_MATH_PLACEHOLDER}"
        html = html.replace(placeholder, expr)
    return html


def render_markdown(text: str) -> str:
    if not text:
        return ""
    text = _render_wikilinks(text)
    stripped = text.lstrip()
    if stripped.startswith("<"):
        return sanitize_article_html(text)
    text, math_placeholders = _protect_math(text)
    html = md_lib.markdown(
        text,
        extensions=_MD_EXTENSIONS,
        extension_configs=_MD_EXTENSION_CONFIGS,
        output_format="html",
    )
    html = _restore_math(html, math_placeholders)
    return sanitize_article_html(html)


def render_talk_markdown(text: str) -> str:
    if not text:
        return ""
    html = md_lib.markdown(text, extensions=["nl2br"], output_format="html")
    return sanitize_html(html, tags=_TALK_ALLOWED_TAGS, attributes=_TALK_ALLOWED_ATTRIBUTES)
