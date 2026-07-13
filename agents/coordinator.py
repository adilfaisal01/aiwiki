from agents.base import BaseAgent, pick_topic, category_for_writer
from agents.historian import Historian
from agents.scientist import Scientist
from agents.critic import Critic
from agents.fact_checker import FactChecker
from agents.quality_improver import QualityImprover
import core.database as db
import random


class Coordinator(BaseAgent):
    def __init__(self):
        super().__init__("Coordinator Kai", "coordinator")
        self.historian = Historian()
        self.scientist = Scientist()
        self.critic = Critic()
        self.fact_checker = FactChecker()
        self.quality_improver = QualityImprover()

    def _track(self, agent_name: str, action: str):
        """Update agent activity in the DB."""
        try:
            db.update_agent_activity(agent_name, action)
        except Exception:
            pass

    def act(self, context: dict) -> dict:
        results = []
        import time as _time

        # Step 1: Review external agent submissions
        reviewed = self._review_external_submissions()
        if reviewed:
            self._track(self.name, f"reviewed external: {reviewed.get('slug', 'unknown')}")
            results.append(reviewed)
            _time.sleep(2.0)

        # Step 2: Improve existing low-quality articles (batch — 3 per cycle)
        for _ in range(3):
            improved = self._improve_low_quality()
            if improved:
                self._track(self.name, f"improved article: {improved.get('slug', 'unknown')}")
                results.append(improved)
                _time.sleep(2.0)
            else:
                break

        # Step 3: Create new articles (batch — 3 per cycle)
        import sqlite3 as _sqlite3
        import threading as _threading
        batch_size = 3
        new_articles = []
        
        for _ in range(batch_size):
            pending = None
            for _attempt in range(5):
                try:
                    pending = db.pop_pending_topic()
                    break
                except _sqlite3.OperationalError as e:
                    if "locked" in str(e) and _attempt < 4:
                        _time.sleep(2.0 * (_attempt + 1))
                        continue
                    raise
            
            if not pending:
                topic, category = pick_topic()
            else:
                topic, category = pending
            
            existing = db.get_article(db.slugify(topic))
            if existing:
                result = self._review_existing(existing)
            else:
                result = self._create_new(topic, category)
            if result:
                results.append(result)
                new_articles.append(result)

        if results:
            return {"action": "multi", "steps": results, "batch_size": len(new_articles)}
        return {"action": "noop", "reason": "nothing to do"}

    def _review_external_submissions(self) -> dict | None:
        """Review the oldest external agent submission."""
        import time, random, sqlite3
        pending = db.get_articles_needing_review()
        if not pending:
            return None
        article = pending[0]
        full = db.get_article(article["slug"])
        if not full:
            return None

        # Track + run critic (no lock held during LLM call)
        db.update_agent_activity(self.critic.name, f"reviewing external: {full['title']}")
        critic_result = self.critic.act({"article": full})

        # Track + run fact-checker
        db.update_agent_activity(self.fact_checker.name, f"fact-checking external: {full['title']}")
        fact_result = self.fact_checker.act({"article": full})

        import time as _time
        _time.sleep(0.5)  # Let SQLite settle

        # All writes in one connection (no LLM calls, so no lock contention)
        conn = db.get_db()
        try:
            p = "?"
            ts = db.now()
            conn.execute(f"INSERT INTO talk_messages (article_id, agent_name, message, parent_id, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                (full["id"], self.critic.name, critic_result["message"], None, ts))
            conn.execute(f"INSERT INTO talk_messages (article_id, agent_name, message, parent_id, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                (full["id"], self.fact_checker.name, fact_result["message"], None, ts))
            conn.execute(f"UPDATE articles SET needs_review = 0 WHERE id = {p}", (full["id"],))
            conn.execute(f"INSERT INTO agent_logs (agent_name, action, article_id, details, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                (self.name, "review_external", full["id"], full["title"], ts))

            if critic_result.get("needs_revision") or fact_result.get("has_issues"):
                conn.execute(f"INSERT INTO talk_messages (article_id, agent_name, message, parent_id, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                    (full["id"], self.name, "Review complete. Some issues were flagged. The article author has been notified.", None, ts))
            else:
                conn.execute(f"INSERT INTO talk_messages (article_id, agent_name, message, parent_id, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                    (full["id"], self.name, "Review complete. No significant issues found. Article is published.", None, ts))
            conn.commit()
        finally:
            conn.close()

        return {"action": "reviewed_external", "article_id": full["id"], "slug": full["slug"]}

    def _improve_low_quality(self) -> dict | None:
        """Improve the worst low-quality article."""
        articles = db.get_all_articles()
        if not articles:
            return None

        candidates_with_feedback = []
        candidates_thin = []

        for article_summary in articles:
            full = db.get_article(article_summary["slug"])
            if not full:
                continue
            if db.is_agent_overview(full):
                continue
            word_count = len(full["content"].split())
            section_count = full["content"].count("## ")

            # Skip articles Quinn already improved recently (within last 10 min)
            from datetime import datetime, timezone
            updated = full.get("updated_at", "")
            if updated:
                try:
                    updated_dt = datetime.fromisoformat(updated)
                    if (datetime.now(timezone.utc) - updated_dt).total_seconds() < 600:
                        continue
                except (ValueError, TypeError):
                    pass

            talk_messages = db.get_talk_messages(full["id"])
            has_unresolved = any(
                "needs_revision" in msg.get("message", "").lower()
                or "flagged" in msg.get("message", "").lower()
                or "please address" in msg.get("message", "").lower()
                for msg in talk_messages
            )

            if has_unresolved:
                candidates_with_feedback.append(full)
            elif word_count < 600 or section_count < 4:
                candidates_thin.append(full)

        if candidates_with_feedback:
            candidate = candidates_with_feedback[0]
            talk_messages = db.get_talk_messages(candidate["id"])
            feedback_text = "\n".join(
                f"- {msg['agent_name']}: {msg['message'][:500]}"
                for msg in talk_messages
                if msg["agent_name"] != self.name
            )
            result = self.quality_improver.act({"article": candidate, "feedback": feedback_text})
            if result.get("action") != "noop":
                db.add_talk_message(
                    candidate["id"], self.name,
                    f"Addressed feedback and improved the article. @{candidate.get('title', '')} has been revised."
                )
                return result

        if not candidates_thin:
            return None

        candidate = min(candidates_thin, key=lambda a: len(a["content"].split()))
        self._track(self.quality_improver.name, f"improving: {candidate.get('title', 'article')}")
        return self.quality_improver.act({"article": candidate})

    def _create_from_pending(self, batch_size: int = 2) -> list[dict]:
        """Create up to batch_size articles from pending See also topics."""
        results = []
        for _ in range(batch_size):
            pending = db.pop_pending_topic()
            if not pending:
                break
            topic, category = pending
            existing = db.get_article(db.slugify(topic))
            if existing:
                result = self._review_existing(existing)
                results.append(result)
            else:
                result = self._create_new(topic, category)
                results.append(result)
        return results

    def _create_new(self, topic: str, category: str) -> dict:
        writer = self.historian if category_for_writer(category) == "history" else self.scientist
        self._track(writer.name, f"writing article: {topic}")
        result = writer.act({"topic": topic})

        content = result["content"]
        article = db.create_article(topic, content, writer.name, f"Initial article on {topic}")
        if not article:
            return {"action": "noop", "reason": f"Article '{topic}' already exists"}

        db.log_agent_action(writer.name, "create_article", article["id"], topic)
        db.add_talk_message(article["id"], writer.name, f"I've drafted an initial article on **{topic}**. Please review.")

        see_also_topics = db.parse_see_also(content)
        for related_topic in see_also_topics:
            db.queue_pending_topic(related_topic, article["id"], category)

        article_data = db.get_article(article["slug"])
        self._track(self.critic.name, f"reviewing: {topic}")
        critic_result = self.critic.act({"article": article_data})
        db.add_talk_message(article["id"], self.critic.name, critic_result["message"])

        self._track(self.fact_checker.name, f"fact-checking: {topic}")
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

        self._track(self.name, f"created article: {topic}")
        return {"action": "created", "article_id": article["id"], "slug": article["slug"], "topic": topic}

    def _review_existing(self, article: dict) -> dict:
        self._track(self.critic.name, f"reviewing: {article['title']}")
        critic_result = self.critic.act({"article": article})
        db.add_talk_message(article["id"], self.critic.name, critic_result["message"])

        self._track(self.fact_checker.name, f"fact-checking: {article['title']}")
        fact_result = self.fact_checker.act({"article": article})
        db.add_talk_message(article["id"], self.fact_checker.name, fact_result["message"])

        db.log_agent_action(self.name, "review_existing", article["id"], article["title"])
        self._track(self.name, f"reviewed: {article['title']}")

        return {"action": "reviewed", "article_id": article["id"], "slug": article["slug"]}
