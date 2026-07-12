from agents.base import BaseAgent
import database as db
import random


class FactChecker(BaseAgent):
    def __init__(self):
        super().__init__("Fact-Checker Finn", "fact_checker")

    def act(self, context: dict) -> dict:
        article = context.get("article")
        if not article:
            return {"action": "noop", "reason": "no article to check"}

        content = article.get("content", "")
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
