"""Standalone script: run one agent loop cycle and exit.

Designed for Railway cron jobs. Shares the same database and env vars
as the main web service. Exits cleanly — no infinite loop, no sleeps.
"""

import logging
import sys

import core.database as db
from agents.base import validate_prompts
from agents.coordinator import Coordinator
from agents.historian import Historian
from agents.scientist import Scientist
from agents.critic import Critic
from agents.fact_checker import FactChecker
from agents.quality_improver import QualityImprover
from core import config

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("aiwiki.agent_loop")


def main():
    prompt_errors = validate_prompts()
    if prompt_errors:
        for err in prompt_errors:
            logger.error("[Prompt Validation] %s", err)

    logger.info("Initializing database...")
    db.init_db()
    db.seed_topics_from_json()

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

    logger.info("Starting agent cycle...")
    try:
        result = coordinator.act({})
        action = result.get("action", "unknown")
        if action == "multi":
            steps = result.get("steps") or []
            for i, step in enumerate(steps, 1):
                step_action = step.get("action", "unknown")
                step_slug = step.get("slug", step.get("topic", ""))
                logger.info("[Step %d/%d] %s: %s", i, len(steps), step_action, step_slug)
            logger.info("Cycle complete: %d step(s)", len(steps))
        elif action == "noop":
            logger.info("Cycle complete: nothing to do (%s)", result.get("reason", ""))
        else:
            logger.info("Cycle complete: %s", action)
    except Exception as e:
        logger.error("Agent cycle failed: %s", e, exc_info=True)
        sys.exit(1)

    logger.info("Agent cycle finished successfully.")


if __name__ == "__main__":
    main()
