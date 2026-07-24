"""Historian agent — writes history and culture articles.

Generates encyclopedic content on historical and cultural topics.
Uses the LLM when available, with template-based fallback for
simulated mode.
"""

from agents.base import BaseAgent, get_templates_for_category, load_prompt
from agents.llm_client import generate_text, is_real_llm_enabled, wrap_content
import random


HISTORY_PROMPT = load_prompt("historian")


class Historian(BaseAgent):
    """Writes encyclopedic articles on history and culture topics."""

    def __init__(self):
        super().__init__("Historian Hal", "history")

    def act(self, context: dict) -> dict:
        """Write an article on the given topic.

        Args:
            context: Dict with key "topic" (string) and optionally
                     "force_topic" (bool) to force topic alignment.

        Returns:
            Dict with keys: action, content, topic.
        """
        topic = context.get("topic", "History")
        category = "history"

        if is_real_llm_enabled():
            content = generate_text(HISTORY_PROMPT.format(topic=topic))
            if content:
                return {"action": "write", "content": content, "topic": topic}

        # Fallback simulated content
        templates = get_templates_for_category(category)
        intro = random.choice(templates["introduction"]).format(topic, category)
        sections = []
        for i in range(random.randint(2, 4)):
            section_title = f"Development of {topic}" if i == 0 else (
                f"Key Events in {topic}" if i == 1 else (
                    f"Legacy of {topic}" if i == 2 else f"Modern Perspectives on {topic}"
                )
            )
            section_body = f"The history of {topic} spans many centuries. "
            section_body += f"Scholars have documented numerous important developments. "
            section_body += f"These events shaped the course of human civilization. "
            section_body += f"Understanding {topic} requires examining multiple perspectives and sources."
            sections.append(f"## {section_title}\n\n{section_body}")

        conclusion = random.choice(templates["conclusion"]).format(topic, category)
        content = f"{intro}\n\n" + "\n\n".join(sections) + f"\n\n{conclusion}"

        return {"action": "write", "content": content, "topic": topic}
