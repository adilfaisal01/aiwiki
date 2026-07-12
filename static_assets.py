import os
import threading
from pathlib import Path

from jinja2 import pass_context

STATIC_DIR = Path(__file__).resolve().parent / "static"

_cache_lock = threading.Lock()
_cache = {"mtime": 0.0, "version": "1"}


def _max_static_mtime() -> float:
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
    request = context.get("request")
    if request is not None and hasattr(request.state, "static_version"):
        version = request.state.static_version
    else:
        version = static_version()
    clean = path.lstrip("/")
    if clean.startswith("static/"):
        clean = clean[7:]
    return f"/static/{clean}?v={version}"
