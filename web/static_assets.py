"""Static asset versioning and URL generation for AIWiki.

Provides cache-busting version strings based on file modification times
and a Jinja2 helper for generating static asset URLs with version query
parameters.
"""

import os
import threading
from pathlib import Path

from jinja2 import pass_context

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_cache_lock = threading.Lock()
_cache = {"mtime": 0.0, "version": "1"}


def _max_static_mtime() -> float:
    """Return the latest modification time of any file under the static directory.

    Returns:
        The maximum mtime as a float, or 0.0 if the directory is missing or empty.
    """
    latest = 0.0
    if not STATIC_DIR.is_dir():
        return latest
    for path in STATIC_DIR.rglob("*"):
        if path.is_file():
            try:
                latest = max(latest, path.stat().st_mtime)
            except OSError:
                continue
    return latest


def static_version() -> str:
    """Return a cache-busting version string for static assets.

    Uses the ``AIWIKI_STATIC_VERSION`` environment variable if set,
    otherwise computes a version from the latest file modification time
    in the static directory. Results are cached and refreshed on change.

    Returns:
        A version string suitable for use as a query parameter.
    """
    env = os.getenv("AIWIKI_STATIC_VERSION", "").strip()
    if env:
        return env
    with _cache_lock:
        latest = _max_static_mtime()
        if latest != _cache["mtime"]:
            _cache["mtime"] = latest
            _cache["version"] = str(int(latest * 1000)) if latest else "1"
        return _cache["version"]


@pass_context
def static_url(context, path: str) -> str:
    """Jinja2 filter to generate a versioned URL for a static asset.

    Prefers a per-request version from ``request.state.static_version``
    over the global version for consistency within a single response.

    Args:
        context: The Jinja2 rendering context (injected by ``@pass_context``).
        path: The asset path, with or without a ``static/`` prefix.

    Returns:
        A URL path like ``/static/css/app.css?v=1234567890``.
    """
    request = context.get("request")
    if request is not None and hasattr(request.state, "static_version"):
        version = request.state.static_version
    else:
        version = static_version()
    clean = path.lstrip("/")
    if clean.startswith("static/"):
        clean = clean[7:]
    return f"/static/{clean}?v={version}"
