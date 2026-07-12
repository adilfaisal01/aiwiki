import os

# Default to SQLite for Railway deployment
raw = os.getenv("AIWIKI_DATABASE_URL", "")
if not raw.startswith("sqlite:///"):
    raw = "sqlite:///./data/aiwiki.db"

DATABASE_URL = raw
LLM_PROVIDER = os.getenv("AIWIKI_LLM_PROVIDER", "simulated")
OPENAI_API_KEY = os.getenv("AIWIKI_OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("AIWIKI_ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("AIWIKI_LLM_MODEL", "gpt-4o")
AGENT_CYCLE_INTERVAL = int(os.getenv("AIWIKI_AGENT_CYCLE_INTERVAL", "300"))
EXTERNAL_RATE_LIMIT = int(os.getenv("AIWIKI_EXTERNAL_RATE_LIMIT", "10"))


def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")
