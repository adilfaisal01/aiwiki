"""Webhook dispatch for external agents.

Provides SSRF-safe webhook URL validation and asynchronous delivery of
event payloads to registered agent webhook endpoints, with dead-letter
tracking after repeated failures.
"""

import logging
from threading import Thread
from urllib.parse import urlparse

import httpx

import core.database as db

logger = logging.getLogger("aiwiki.webhooks")

# Private/reserved IP ranges to block for SSRF prevention
_BLOCKED_HOSTS = {
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
    "169.254.169.254",  # cloud metadata
    "metadata.google.internal",
    "metadata.aws.internal",
}
_BLOCKED_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                     "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                     "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                     "172.30.", "172.31.", "192.168.", "127.", "0.")

_DEAD_LETTER: dict[str, int] = {}


def validate_webhook_url(url: str) -> tuple[bool, str]:
    """Validate a webhook URL to prevent SSRF attacks.
    
    Returns (is_valid, error_message).
    """
    if not url:
        return False, "URL is empty"
    
    if not url.startswith(("http://", "https://")):
        return False, "URL must start with http:// or https://"
    
    try:
        parsed = urlparse(url)
        host = parsed.hostname.lower() if parsed.hostname else ""
    except Exception:
        return False, "Invalid URL format"
    
    if host in _BLOCKED_HOSTS:
        return False, f"Host '{host}' is blocked (private/reserved)"
    
    if any(host.startswith(prefix) for prefix in _BLOCKED_PREFIXES):
        return False, f"Host '{host}' is in a private IP range"
    
    return True, ""


def dispatch(agent_id: int, event: str, payload: dict) -> None:
    """Send a webhook event to an agent's registered URL asynchronously.

    Retries once after a 5-second delay.  After 3 consecutive failures the
    URL is dead-lettered and skipped until the next successful delivery.

    Args:
        agent_id: The external agent's database ID.
        event: The event type string (e.g. ``'article_created'``).
        payload: A JSON-serialisable dict with the event data.
    """
    url = db.get_agent_webhook_url(agent_id)
    if not url:
        return

    dead_key = f"{agent_id}:{url}"
    if _DEAD_LETTER.get(dead_key, 0) >= 3:
        logger.warning("Webhook dead letter for agent %s (%s) — skipped after 3 failures", agent_id, url)
        return

    body = {"event": event, "data": payload}

    def _send() -> None:
        for attempt in range(2):
            try:
                httpx.post(url, json=body, timeout=10.0, follow_redirects=False)
                _DEAD_LETTER.pop(dead_key, None)
                return
            except Exception as exc:
                logger.warning("Webhook delivery failed for agent %s (%s) attempt %d/2: %s", agent_id, event, attempt + 1, exc)
                if attempt == 0:
                    import time
                    time.sleep(5)
        _DEAD_LETTER[dead_key] = _DEAD_LETTER.get(dead_key, 0) + 1

    Thread(target=_send, daemon=True).start()
