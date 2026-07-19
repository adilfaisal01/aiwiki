#!/usr/bin/env python3
"""Standalone agent cycle — runs one coordinator.act({}) cycle and exits.
Used by GitHub Actions cron to trigger the agent loop."""

import os, sys, logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.database as db
from core import config
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
    db.init_db()
    seed_database()

    historian = Historian()
    scientist = Scientist()
    critic = Critic()
    fact_checker = FactChecker()
    quality_improver = QualityImprover(historian=historian, scientist=scientist)

    coordinator = Coordinator(
        historian=historian, scientist=scientist, critic=critic,
        fact_checker=fact_checker, quality_improver=quality_improver,
    )

    try:
        result = coordinator.act({})
        action = result.get("action")
        logger.info("[Agent] Cycle complete — action: %s", action)
        return True
    except Exception as e:
        logger.error("[Agent] Cycle failed: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    success = run_cycle()
    sys.exit(0 if success else 1)
