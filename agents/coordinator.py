from agents.base import BaseAgent, pick_topic, category_for_writer
from agents.historian import Historian
from agents.scientist import Scientist
from agents.critic import Critic
from agents.fact_checker import FactChecker
from agents.quality_improver import QualityImprover
import database as db
import random


class Coordinator(BaseAgent):
    def __init__(self):
        super().__init__("Coordinator Kai", "coordinator")
        self.historian = Historian()
        self.scientist = Scientist()
        self.critic = Critic()
        self.fact_checker = FactChecker()
        self.quality_improver = QualityImprover()

    def act(self, context: dict) -> dict:
        # First priority: improve existing low-quality articles
        improved = self._improve_low_quality()
        if improved:
            return improved

        # Otherwise create or review a new article
        topic, category = pick_topic()
        existing = db.get_article(db.slugify(topic))
        if existing:
            return self._review_existing(existing)
        return self._create_new(topic, category)

    def _improve_low_quality(self) -> dict | None:
        articles = db.get_all_articles()
        if not articles:
            return None

        # Find short or thin articles
        candidates = []
        for article_summary in articles:
            full = db.get_article(article_summary["slug"])
            if not full:
                continue
            if db.is_agent_overview(full):
                continue
            word_count = len(full["content"].split())
            section_count = full["content"].count("## ")
            if word_count < 600 or section_count < 4:
                candidates.append(full)

        if not candidates:
            return None

        # Pick the shortest or thinnest
        candidate = min(candidates, key=lambda a: len(a["content"].split()))
        return self.quality_improver.act({"article": candidate})

    def _create_new(self, topic: str, category: str) -> dict:
        writer = self.historian if category_for_writer(category) == "history" else self.scientist
        result = writer.act({"topic": topic})

        content = result["content"]
        article = db.create_article(topic, content, writer.name, f"Initial article on {topic}")
        if not article:
            return {"action": "noop", "reason": f"Article '{topic}' already exists"}

        db.log_agent_action(writer.name, "create_article", article["id"], topic)
        db.add_talk_message(article["id"], writer.name, f"I've drafted an initial article on **{topic}**. Please review.")

        article_data = db.get_article(article["slug"])
        critic_result = self.critic.act({"article": article_data})
        db.add_talk_message(article["id"], self.critic.name, critic_result["message"])

        fact_result = self.fact_checker.act({"article": article_data})
        db.add_talk_message(article["id"], self.fact_checker.name, fact_result["message"])

        if critic_result.get("needs_revision") or fact_result.get("has_issues"):
            db.add_talk_message(
                article["id"], self.name,
                f"Review complete. Some issues were flagged. @{writer.name}, please address the feedback."
            )
        else:
            db.add_talk_message(
                article["id"], self.name,
                "Review complete. No significant issues found. Article is published."
            )

        return {"action": "created", "article_id": article["id"], "slug": article["slug"], "topic": topic}

    def _review_existing(self, article: dict) -> dict:
        critic_result = self.critic.act({"article": article})
        db.add_talk_message(article["id"], self.critic.name, critic_result["message"])

        fact_result = self.fact_checker.act({"article": article})
        db.add_talk_message(article["id"], self.fact_checker.name, fact_result["message"])

        db.log_agent_action(self.name, "review_existing", article["id"], article["title"])

        return {"action": "reviewed", "article_id": article["id"], "slug": article["slug"]}
