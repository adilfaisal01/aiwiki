import os
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_raw_db = os.getenv("AIWIKI_DATABASE_URL", "").strip()
if not _raw_db:
    DATABASE_URL = "sqlite:///./data/aiwiki.db"
elif _raw_db.startswith("sqlite:///") or _raw_db.startswith(("postgresql://", "postgres://")):
    DATABASE_URL = _raw_db
else:
    DATABASE_URL = "sqlite:///./data/aiwiki.db"

LLM_PROVIDER = os.getenv("AIWIKI_LLM_PROVIDER", "simulated")
LLM_MODEL = os.getenv("AIWIKI_LLM_MODEL", "llama3.2")

OPENAI_API_KEY = os.getenv("AIWIKI_OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("AIWIKI_ANTHROPIC_API_KEY", "")
OLLAMA_API_KEY = os.getenv("AIWIKI_OLLAMA_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("AIWIKI_OLLAMA_BASE_URL", "http://localhost:11434")

AGENT_CYCLE_INTERVAL = int(os.getenv("AIWIKI_AGENT_CYCLE_INTERVAL", "300"))
EXTERNAL_RATE_LIMIT = int(os.getenv("AIWIKI_EXTERNAL_RATE_LIMIT", "10"))
REGISTRATION_RATE_LIMIT = int(os.getenv("AIWIKI_REGISTRATION_RATE_LIMIT", "5"))
LOG_LEVEL = os.getenv("AIWIKI_LOG_LEVEL", "INFO").upper()
WIKI_EDIT_ENABLED = os.getenv("AIWIKI_WIKI_EDIT_ENABLED", "false").lower() in ("1", "true", "yes")
DISABLE_AGENT_LOOP = os.getenv("AIWIKI_DISABLE_AGENT_LOOP", "false").lower() in ("1", "true", "yes")
AGENT_ONLINE_THRESHOLD_SECONDS = int(os.getenv("AIWIKI_AGENT_ONLINE_THRESHOLD", "300"))


def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")


def get_postgres_config() -> dict:
    parsed = urlparse(DATABASE_URL)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "dbname": (parsed.path or "/").lstrip("/"),
        "user": parsed.username or "",
        "password": parsed.password or "",
    }
