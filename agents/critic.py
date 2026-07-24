"""Critic agent — reviews article structure, tone, and quality.

Provides structured feedback on articles, flagging issues like
insufficient length, missing sections, or poor structure. Uses the
LLM when available, with a rule-based fallback.
"""

from agents.base import BaseAgent, load_prompt
from agents.llm_client import generate_text, is_real_llm_enabled, wrap_content, detect_injection
import random


REVIEW_PROMPT = load_prompt("critic")


class Critic(BaseAgent):
    """Reviews article structure, tone, and quality.

    Provides structured feedback and flags issues such as insufficient
    length, missing section headings, or poor structure. Uses the LLM
    when available, with a rule-based fallback for simulated mode.
    """

    def __init__(self):
        super().__init__("Critic Carla", "critic")

    def act(self, context: dict) -> dict:
        """Review an article and return structured feedback.

        Args:
            context: Dict with key "article" containing the article data
                     (must have "title" and "content" keys).

        Returns:
            Dict with keys: action, message, suggestions, needs_revision.
        """
        article = context.get("article")
        if not article:
            return {"action": "noop", "reason": "no article to review"}

        topic = article.get("title", "this topic")
        content = article.get("content", "")

        if is_real_llm_enabled():
            if detect_injection(content):
                return {
                    "action": "review",
                    "message": f"**Review by {self.name}:**\n\n⚠️ This article appears to contain prompt injection attempts and was flagged by security. No review was performed.",
                    "suggestions": ["Article flagged for security review"],
                    "needs_revision": True,
                }
            review = generate_text(REVIEW_PROMPT.format(topic=topic, content=wrap_content(content)))
            if review:
                suggestions = [
                    line.strip("- ").strip()
                    for line in review.splitlines()
                    if line.strip().startswith("-")
                ]
                if not suggestions:
                    suggestions = [review.strip()]
                positive_markers = ("excellent", "well-structured", "no major issues", "already strong")
                needs_revision = len(suggestions) > 1
                if len(suggestions) == 1 and any(m in suggestions[0].lower() for m in positive_markers):
                    needs_revision = False
                return {
                    "action": "review",
                    "message": f"**Review by {self.name}:**\n\n{review}",
                    "suggestions": suggestions,
                    "needs_revision": needs_revision,
                }

        # Fallback review (used when LLM is unavailable or returns empty)
        suggestions = []

        if len(content) < 200:
            suggestions.append("This article is quite short. Consider expanding it with more detail.")
        if "## " not in content:
            suggestions.append("The article lacks section headings. Adding structure would improve readability.")
        if len(content.split(".")) < 5:
            suggestions.append("The article has very few sentences. More content is needed.")

        if not suggestions:
            suggestions.append("The article looks well-structured. No major issues found.")

        message = f"**Review by {self.name}:**\n\n" + "\n".join(f"- {s}" for s in suggestions)

        return {
            "action": "review",
            "message": message,
            "suggestions": suggestions,
            "needs_revision": len(suggestions) > 1,
        }
