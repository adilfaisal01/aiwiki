"""Fact-checker agent — validates factual claims in articles.

Scans article content for vague attributions, absolute language, and
other potential factual issues. Uses the LLM when available, with a
rule-based fallback for simulated mode.
"""

from agents.base import BaseAgent, load_prompt
from agents.llm_client import generate_text, is_real_llm_enabled, wrap_content, detect_injection
import random


FACT_CHECK_PROMPT = load_prompt("fact_checker")


class FactChecker(BaseAgent):
    """Validates factual claims in articles.

    Scans for vague attributions, absolute language, and other
    potential issues. Uses the LLM when available, with a rule-based
    fallback for simulated mode.
    """

    def __init__(self):
        super().__init__("Fact-Checker Finn", "fact_checker")

    def act(self, context: dict) -> dict:
        """Fact-check an article and return findings.

        Args:
            context: Dict with key "article" containing the article data
                     (must have "title" and "content" keys).

        Returns:
            Dict with keys: action, message, issues, has_issues.
        """
        article = context.get("article")
        if not article:
            return {"action": "noop", "reason": "no article to check"}

        topic = article.get("title", "this topic")
        content = article.get("content", "")

        if is_real_llm_enabled():
            if detect_injection(content):
                return {
                    "action": "fact_check",
                    "message": f"**Fact-check by {self.name}:**\n\n⚠️ This article appears to contain prompt injection attempts and was flagged by security. No fact-check was performed.",
                    "issues": ["Article flagged for security review"],
                    "has_issues": True,
                }
            check = generate_text(FACT_CHECK_PROMPT.format(topic=topic, content=wrap_content(content)))
            if check:
                issues = [line.strip("- ").strip() for line in check.splitlines() if line.strip().startswith("-")]
                if not issues:
                    issues = ["No factual issues detected. The article appears well-sourced."]
                message = f"**Fact-check by {self.name}:**\n\n" + "\n".join(f"- {i}" for i in issues)
                return {
                    "action": "fact_check",
                    "message": message,
                    "issues": issues,
                    "has_issues": any("No factual issues" not in i for i in issues),
                }

        # Fallback fact-check (used when LLM is unavailable or returns empty)
        issues = []

        vague_phrases = ["some people say", "it is believed", "many think", "some claim", "it is said"]
        for phrase in vague_phrases:
            if phrase in content.lower():
                issues.append(f"Vague attribution: '{phrase}' — consider adding specific sources.")

        if "always" in content.lower() or "never" in content.lower():
            issues.append("Absolute language detected ('always'/'never'). Consider qualifying these claims.")

        if "!" in content:
            issues.append("Exclamation marks found. Encyclopedic tone is preferred.")

        if not issues:
            issues.append("No factual issues detected. The article appears well-sourced.")

        message = f"**Fact-check by {self.name}:**\n\n" + "\n".join(f"- {i}" for i in issues)

        return {
            "action": "fact_check",
            "message": message,
            "issues": issues,
            "has_issues": any("No factual issues" not in i for i in issues),
        }
