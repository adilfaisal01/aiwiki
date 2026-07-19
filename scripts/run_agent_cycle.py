#!/usr/bin/env python3
"""Standalone agent cycle script — runs one coordinator.act({}) cycle and exits.
Used by GitHub Actions cron to trigger the agent loop without a daemon thread."""

import os, sys, logging, time

# Add project root to path so we can import aiwiki modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Must set env before importing config
os.environ.setdefault("AIWIKI_DATABASE_URL", os.getenv("AIWIKI_DATABASE_URL", ""))
os.environ.setdefault("AIWIKI_LLM_PROVIDER", os.getenv("AIWIKI_LLM_PROVIDER", "ollama"))
os.environ.setdefault("AIWIKI_OLLAMA_BASE_URL", os.getenv("AIWIKI_OLLAMA_BASE_URL", "http://localhost:11434"))

import core.database as db
from core import config
from agents.base import validate_prompts
from agents.coordinator import Coordinator
from agents.historian import Historian
from agents.scientist import Scientist
from agents.critic import Critic
from agents.fact_checker import FactChecker
from agents.quality_improver import QualityImprover
from scripts.seed_data import seed_database

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("agent-cron")


def run_cycle():
    """Run one agent cycle — same logic as main.py's agent_loop() but runs once."""
    logger.info("[Agent] Starting agent cycle via cron trigger")

    # Initialize DB
    db.init_db()
    seed_database()

    # Set up agents (same as main.py)
    historian = Historian()
    scientist = Scientist()
    critic = Critic()
    fact_checker = FactChecker()
    quality_improver = QualityImprover(historian=historian, scientist=scientist)

    coordinator = Coordinator(
        historian=historian,
        scientist=scientist,
        critic=critic,
        fact_checker=fact_checker,
        quality_improver=quality_improver,
    )

    # Run one cycle
    try:
        result = coordinator.act({})
        action = result.get("action")
        logger.info("[Agent] Cycle complete — action: %s", action)

        if action == "multi":
            steps = result.get("steps") or []
            logger.info("[Agent] %d step(s) completed", len(steps))
        elif action == "batch":
            count = result.get("count", 0)
            logger.info("[Agent] %d batch action(s) completed", count)
        elif action == "created":
            logger.info("[Agent] Created article: %s", result.get("topic"))
        elif action == "reviewed":
            logger.info("[Agent] Reviewed: %s", result.get("slug"))
        elif action == "improved":
            logger.info("[Agent] Improved: %s", result.get("slug"))

        return True
    except Exception as e:
        logger.error("[Agent] Cycle failed: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Agent cycle triggered by GitHub Actions cron")
    logger.info("=" * 50)
    success = run_cycle()
    sys.exit(0 if success else 1)
