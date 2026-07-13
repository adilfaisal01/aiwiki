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
    url = db.get_agent_webhook_url(agent_id)
    if not url:
        return

    body = {"event": event, "data": payload}

    def _send() -> None:
        try:
            httpx.post(url, json=body, timeout=10.0)
        except Exception as exc:
            logger.warning("Webhook delivery failed for agent %s (%s): %s", agent_id, event, exc)

    Thread(target=_send, daemon=True).start()
