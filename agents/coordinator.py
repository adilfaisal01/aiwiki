import json
import logging
import re

from agents.base import BaseAgent, pick_topic, category_for_writer, append_topics, load_prompt
from agents.llm_client import generate_text, is_real_llm_enabled
from agents.md_to_blueprint import markdown_to_blueprint
from wiki.article_blueprint import render_article_blueprint, ArticleBlueprint, Infobox, InfoboxEntry
import core.database as db
import random


logger = logging.getLogger("aiwiki.coordinator")

INFOBOX_GENERATE_PROMPT = load_prompt("infobox_generate")


class Coordinator(BaseAgent):
    def __init__(self, historian, scientist, critic, fact_checker, quality_improver):
        super().__init__("Coordinator Kai", "coordinator")
        self.historian = historian
        self.scientist = scientist
        self.critic = critic
        self.fact_checker = fact_checker
        self.quality_improver = quality_improver

    def _track(self, agent_name: str, action: str):
        """Update agent activity in the DB."""
        try:
            db.update_agent_activity(agent_name, action)
        except Exception as e:
            logger.warning("Failed to track agent activity for %s: %s", agent_name, e)

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
        batch_size = 3
        new_articles = []
        existing_slugs = {a["slug"] for a in db.get_all_articles()}
        writer_order = [self.historian, self.scientist, random.choice([self.historian, self.scientist])]

        for writer in writer_order:
            target_cat = "history" if writer == self.historian else "science"
            topic, category = pick_topic(category=target_cat, exclude_slugs=existing_slugs)
            slug = db.slugify(topic)
            if slug in existing_slugs:
                topic, category = pick_topic(exclude_slugs=existing_slugs)
                slug = db.slugify(topic)
                if slug in existing_slugs:
                    continue
            result = self._create_new(topic, category)
            if result:
                results.append(result)
                new_articles.append(result)
                existing_slugs.add(slug)

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
            # Cap improvement rounds at 3
            improve_count = db.count_improvements(full["id"], self.quality_improver.name)
            if improve_count >= 3:
                continue

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

        # TOPIC VERIFICATION (wrapped so it can't crash the loop)
        try:
            topic_verified = self._verify_topic_alignment(topic, content)
            if not topic_verified:
                self._track(writer.name, f"rewriting: {topic} (topic mismatch)")
                result = writer.act({"topic": topic, "force_topic": True})
                content = result["content"]
                if not self._verify_topic_alignment(topic, content):
                    content = f"# {topic}\n\n" + content
        except Exception as e:
            logger.warning("Topic verification failed for '%s': %s", topic, e)

        # Build complete article with infobox
        try:
            rendered = self._build_article(topic, category, content, writer.name)
        except Exception as e:
            logger.warning("Article build failed for '%s': %s", topic, e)
            rendered = content

        article = db.create_article(topic, rendered, writer.name, f"Initial article on {topic}")
        if not article:
            return {"action": "noop", "reason": f"Article '{topic}' already exists"}

        db.log_agent_action(writer.name, "create_article", article["id"], topic)
        db.add_talk_message(article["id"], writer.name, f"I've drafted an initial article on **{topic}**. Please review.")

        see_also_topics = db.parse_see_also(content)
        if see_also_topics:
            append_topics([(t, category) for t in see_also_topics])

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

    def _generate_infobox(self, title: str, category: str, content: str) -> Infobox | None:
        if not is_real_llm_enabled():
            return None
        prompt = INFOBOX_GENERATE_PROMPT.format(title=title, category=category, content=content[:2000])
        result = generate_text(prompt, temperature=0.3, max_tokens=500)
        if not result:
            return None
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if not json_match:
            return None
        try:
            data = json.loads(json_match.group(0))
            if not isinstance(data, dict) or "rows" not in data:
                return None
            rows = []
            for row in data["rows"]:
                if not isinstance(row, dict):
                    continue
                rows.append(InfoboxEntry(
                    kind=row.get("kind", "field"),
                    title=row.get("title"),
                    label=row.get("label"),
                    value=row.get("value"),
                ))
            return Infobox(title=data.get("title", title), rows=rows)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to parse infobox for '%s': %s", title, e)
            return None

    def _build_article(self, topic: str, category: str, content: str, agent_name: str) -> str:
        blueprint = markdown_to_blueprint(content, topic)
        infobox = self._generate_infobox(topic, category, content)
        if infobox:
            blueprint.infobox = infobox
            self._track(agent_name, f"infobox: {topic}")
        rendered = render_article_blueprint(blueprint)
        if rendered and len(rendered) > 100:
            has_sections = len(blueprint.sections) > 0
            has_lead = len(blueprint.lead) > 0 and len(blueprint.lead[0]) > 50
            if has_sections or has_lead:
                self._track(agent_name, f"blueprint: {topic}")
                return rendered
        fallback = ArticleBlueprint(
            infobox=infobox,
            lead=[content],
            sections=[],
            see_also=[],
            references=[],
            external_links=[],
        )
        rendered = render_article_blueprint(fallback)
        if rendered and len(rendered) > 50:
            return rendered
        return content

    def _verify_topic_alignment(self, topic: str, content: str) -> bool:
        """Check that the article content actually matches the given topic."""
        topic_lower = topic.lower()
        # Check if the topic name appears in the first 500 chars of content
        first_500 = content[:500].lower()
        # Extract key words from the topic (skip common words)
        key_words = [w.lower() for w in topic.split() if len(w) > 3]
        if not key_words:
            return True  # Can't verify single-word topics
        # Check that at least 50% of key words appear in the content
        matches = sum(1 for w in key_words if w in first_500)
        return matches >= max(1, len(key_words) // 2)

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
