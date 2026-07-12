from agents.base import BaseAgent
import database as db
import random


class Critic(BaseAgent):
    def __init__(self):
        super().__init__("Critic Carla", "critic")

    def act(self, context: dict) -> dict:
        article = context.get("article")
        if not article:
            return {"action": "noop", "reason": "no article to review"}

        content = article.get("content", "")
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
