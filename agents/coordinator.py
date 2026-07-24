"""Agent coordinator — orchestrates the multi-agent article pipeline.

Runs in a background thread during the app lifespan. Each cycle it
reviews external submissions, improves low-quality articles, and
creates new articles using the specialist writer agents.
"""

import json
import logging
import re
import time as _time

from agents.base import BaseAgent, pick_topic, category_for_writer, append_topics, load_prompt
from agents.llm_client import generate_text, is_real_llm_enabled
from agents.md_to_blueprint import markdown_to_blueprint
from core.log_sanitize import sanitize as sanitize_log
from wiki.article_blueprint import render_article_blueprint, ArticleBlueprint, Infobox, InfoboxEntry
import core.database as db
import random


logger = logging.getLogger("aiwiki.coordinator")

_coordinator_backoff_until: float = 0
_coordinator_empty_cycles: int = 0


def _coordinator_circuit_breaker() -> bool:
    """Check whether the coordinator circuit breaker is open.

    After several empty cycles the coordinator backs off to avoid
    busy-waiting when no work is available.

    Returns:
        True if the coordinator should proceed, False if backing off.
    """
    global _coordinator_backoff_until, _coordinator_empty_cycles
    if _time.time() < _coordinator_backoff_until:
        return False
    return True


def _coordinator_record_empty_cycle():
    """Record an empty cycle and potentially open the circuit breaker.

    After 3 consecutive empty cycles, applies exponential backoff
    (capped at 300 seconds).
    """
    global _coordinator_backoff_until, _coordinator_empty_cycles
    _coordinator_empty_cycles += 1
    if _coordinator_empty_cycles >= 3:
        backoff = min(300, 60 * (2 ** (_coordinator_empty_cycles - 3)))
        _coordinator_backoff_until = _time.time() + backoff
        logger.warning("Coordinator circuit breaker: %d empty cycles, backing off %ds", _coordinator_empty_cycles, backoff)


def _coordinator_record_success():
    """Reset the circuit breaker after a successful cycle."""
    global _coordinator_backoff_until, _coordinator_empty_cycles
    _coordinator_backoff_until = 0
    _coordinator_empty_cycles = 0

INFOBOX_GENERATE_PROMPT = load_prompt("infobox_generate")


class Coordinator(BaseAgent):
    """Orchestrates the multi-agent article pipeline.

    Each cycle the coordinator:
    1. Reviews external agent submissions (critic + fact-checker).
    2. Improves low-quality or feedback-flagged articles.
    3. Creates new articles using historian/scientist agents.
    """

    def __init__(self, historian, scientist, critic, fact_checker, quality_improver):
        """Initialize the coordinator with all sub-agents.

        Args:
            historian: Historian agent instance.
            scientist: Scientist agent instance.
            critic: Critic agent instance.
            fact_checker: FactChecker agent instance.
            quality_improver: QualityImprover agent instance.
        """
        super().__init__("Coordinator Kai", "coordinator")
        self.historian = historian
        self.scientist = scientist
        self.critic = critic
        self.fact_checker = fact_checker
        self.quality_improver = quality_improver

    def _track(self, agent_name: str, action: str):
        """Update agent activity in the DB.

        Args:
            agent_name: Name of the agent to track.
            action: Description of the action performed.
        """
        try:
            db.update_agent_activity(agent_name, action)
        except Exception as e:
            logger.warning("Failed to track agent activity for %s: %s", agent_name, sanitize_log(str(e)))

    def act(self, context: dict) -> dict:
        """Run one full coordinator cycle.

        Steps: review external submissions, improve low-quality articles,
        create new articles. Uses ThreadPoolExecutor for parallel work.

        Args:
            context: Unused but required by the BaseAgent interface.

        Returns:
            Dict with "action" key ("multi", "noop") and results.
        """
        if not _coordinator_circuit_breaker():
            return {"action": "noop", "reason": "circuit breaker open"}

        results = []
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Step 1: Review external agent submissions (parallel — up to 3)
        with ThreadPoolExecutor(max_workers=3) as pool:
            review_futures = [pool.submit(self._review_external_submissions) for _ in range(3)]
            for future in as_completed(review_futures):
                try:
                    reviewed = future.result()
                    if reviewed and reviewed.get("action") != "noop":
                        slug = reviewed.get('slug', 'unknown')
                        logger.info("[Step] Reviewed external submission: %s", slug)
                        self._track(self.name, f"reviewed external: {slug}")
                        results.append(reviewed)
                except Exception as e:
                    logger.warning("Review submission failed: %s", sanitize_log(str(e)))

        # Step 2: Improve existing low-quality articles (up to 3 per cycle)
        try:
            for improved in self._improve_low_quality():
                if improved and improved.get("action") != "noop":
                    slug = improved.get('slug', 'unknown')
                    logger.info("[Step] Improved article: %s", slug)
                    self._track(self.name, f"improved article: {slug}")
                    results.append(improved)
        except Exception as e:
            logger.warning("Improve low quality failed: %s", sanitize_log(str(e)))

        # Step 3: Create new articles (parallel — up to 3)
        new_articles = []
        writer_order = [self.historian, self.scientist, random.choice([self.historian, self.scientist])]

        def _try_create(writer):
            target_cat = "history" if writer == self.historian else "science"
            topic, category = pick_topic(category=target_cat)
            if not topic:
                logger.info("[Create] no topics available in %s", target_cat)
                return None
            slug = db.slugify(topic)
            logger.info("[Step] Creating article: %s (slug: %s, category: %s)", topic, slug, category)
            result = self._create_new(topic, category)
            if result and result.get("action") != "noop":
                return (result, topic, slug)
            logger.info("[Create] _create_new returned noop for %s: %s", topic, result)
            return None

        with ThreadPoolExecutor(max_workers=3) as pool:
            create_futures = [pool.submit(_try_create, w) for w in writer_order]
            for future in as_completed(create_futures):
                try:
                    outcome = future.result()
                    if outcome:
                        result, topic, slug = outcome
                        results.append(result)
                        new_articles.append(result)
                        logger.info("[Step] Created article: %s (slug: %s)", topic, result.get('slug', ''))
                except Exception as e:
                    logger.warning("Article creation failed: %s", sanitize_log(str(e)))

        if results:
            _coordinator_record_success()
            return {"action": "multi", "steps": results, "batch_size": len(new_articles)}
        _coordinator_record_empty_cycle()
        return {"action": "noop", "reason": "nothing to do"}

    def _review_external_submissions(self) -> dict | None:
        """Review the oldest external agent submission.

        Runs the critic and fact-checker on the oldest pending article,
        records their feedback as talk messages, and marks the article
        as reviewed.

        Returns:
            Result dict with action "reviewed_external", or None if no
            pending submissions exist.
        """
        import time, random, sqlite3
        pending = db.get_articles_needing_review()
        if not pending:
            return None
        article = pending[0]
        full = db.get_article(article["slug"])
        if not full:
            return None

        # Track + run critic (no lock held during LLM call)
        try:
            db.update_agent_activity(self.critic.name, f"reviewing external: {full['title']}")
            critic_result = self.critic.act({"article": full})
        except Exception as e:
            logger.warning("Critic review failed for '%s': %s", full["title"], sanitize_log(str(e)))
            return None

        # Track + run fact-checker
        try:
            db.update_agent_activity(self.fact_checker.name, f"fact-checking external: {full['title']}")
            fact_result = self.fact_checker.act({"article": full})
        except Exception as e:
            logger.warning("Fact-checker failed for '%s': %s", full["title"], sanitize_log(str(e)))
            return None

        import time as _time
        _time.sleep(0.5)  # Let SQLite settle

        # All writes in one connection (no LLM calls, so no lock contention)
        conn = db.get_db()
        try:
            p = db._param_style()
            ts = db.now()
            db._execute(conn, f"INSERT INTO talk_messages (article_id, agent_name, message, parent_id, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                (full["id"], self.critic.name, critic_result["message"], None, ts))
            db._execute(conn, f"INSERT INTO talk_messages (article_id, agent_name, message, parent_id, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                (full["id"], self.fact_checker.name, fact_result["message"], None, ts))
            db._execute(conn, f"UPDATE articles SET needs_review = 0 WHERE id = {p}", (full["id"],))
            db._execute(conn, f"INSERT INTO agent_logs (agent_name, action, article_id, details, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                (self.name, "review_external", full["id"], full["title"], ts))

            if critic_result.get("needs_revision") or fact_result.get("has_issues"):
                db._execute(conn, f"INSERT INTO talk_messages (article_id, agent_name, message, parent_id, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                    (full["id"], self.name, "Review complete. Some issues were flagged. The article author has been notified.", None, ts))
            else:
                db._execute(conn, f"INSERT INTO talk_messages (article_id, agent_name, message, parent_id, timestamp) VALUES ({p}, {p}, {p}, {p}, {p})",
                    (full["id"], self.name, "Review complete. No significant issues found. Article is published.", None, ts))
            conn.commit()
        finally:
            conn.close()

        return {"action": "reviewed_external", "article_id": full["id"], "slug": full["slug"]}

    def _improve_low_quality(self) -> list[dict]:
        """Improve up to 3 low-quality articles per cycle.

        Prioritizes articles with unresolved feedback, then thin articles
        (under 600 words or fewer than 4 sections). Skips articles that
        have already been improved 3+ times.

        Returns:
            List of result dicts from the quality improver.
        """
        articles = db.get_all_articles()
        if not articles:
            return []

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

            from datetime import datetime, timezone
            updated = full.get("updated_at", "")
            if updated:
                try:
                    updated_dt = datetime.fromisoformat(updated)
                    if (datetime.now(timezone.utc) - updated_dt).total_seconds() < 60:
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
                feedback_messages = [m for m in talk_messages if m["agent_name"] != self.name]
                if feedback_messages:
                    latest_feedback_ts = max(m.get("timestamp", "") for m in feedback_messages)
                    article_updated = full.get("updated_at", "")
                    if article_updated and latest_feedback_ts and article_updated > latest_feedback_ts:
                        db.add_talk_message(
                            full["id"], self.name,
                            f"Feedback has been addressed by an external contributor. @{full.get('title', '')} has been revised."
                        )
                        has_unresolved = False

            improve_count = db.count_improvements(full["id"], self.quality_improver.name)
            if improve_count >= 3:
                continue

            if has_unresolved:
                candidates_with_feedback.append(full)
            elif word_count < 600 or section_count < 4:
                candidates_thin.append(full)

        results = []
        max_improvements = 3

        for candidate in candidates_with_feedback[:max_improvements]:
            try:
                talk_messages = db.get_talk_messages(candidate["id"])
                feedback_text = "\n".join(
                    f"- {msg['agent_name']}: {msg['message'][:500]}"
                    for msg in talk_messages
                    if msg["agent_name"] != self.name
                )
                result = self.quality_improver.act({"article": candidate, "feedback": feedback_text})
                if result.get("action") != "noop":
                    self._rebuild_article_infobox(candidate["id"], candidate["title"])
                    db.add_talk_message(
                        candidate["id"], self.name,
                        f"Addressed feedback and improved the article. @{candidate.get('title', '')} has been revised."
                    )
                    results.append(result)
                    if len(results) >= max_improvements:
                        return results
            except Exception as e:
                logger.warning("Failed to improve article '%s': %s", candidate.get("title", "unknown"), sanitize_log(str(e)))

        remaining = max_improvements - len(results)
        candidates_thin.sort(key=lambda a: len(a["content"].split()))

        for candidate in candidates_thin[:remaining]:
            try:
                self._track(self.quality_improver.name, f"improving: {candidate.get('title', 'article')}")
                result = self.quality_improver.act({"article": candidate})
                if result.get("action") != "noop":
                    self._rebuild_article_infobox(candidate["id"], candidate["title"])
                    results.append(result)
                    if len(results) >= max_improvements:
                        break
            except Exception as e:
                logger.warning("Failed to improve thin article '%s': %s", candidate.get("title", "unknown"), sanitize_log(str(e)))

        return results

    def _create_from_pending(self, batch_size: int = 2) -> list[dict]:
        """Create up to batch_size articles from pending See also topics.

        Pops topics from the pending queue and either creates a new
        article or reviews an existing one if the slug already exists.

        Args:
            batch_size: Maximum number of articles to create.

        Returns:
            List of result dicts from article creation or review.
        """
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

    def _rebuild_article_infobox(self, article_id: int, title: str):
        """Regenerate the infobox for an article after improvement.

        Re-parses the article content into a blueprint, generates a new
        infobox, and updates the stored article.

        Args:
            article_id: Database ID of the article.
            title: Article title.
        """
        try:
            article = db.get_article_by_id(article_id)
            if not article:
                return
            content = article["content"]
            blueprint = markdown_to_blueprint(content, title)
            infobox = self._generate_infobox(title, "", content)
            if infobox:
                blueprint.infobox = infobox
            rendered = render_article_blueprint(blueprint)
            if rendered and len(rendered) > 50:
                db.update_article(article_id, rendered, self.name, "Rebuilt infobox after improvement")
        except Exception as e:
            logger.warning("Failed to rebuild infobox for '%s': %s", title, sanitize_log(str(e)))

    def _create_new(self, topic: str, category: str) -> dict:
        """Create a new article on the given topic.

        Selects the appropriate writer agent, generates content, verifies
        topic alignment, builds the article with infobox, persists it,
        and runs critic + fact-checker review.

        Args:
            topic: Article topic/title.
            category: Topic category (determines which writer to use).

        Returns:
            Result dict with action "created" or "noop".
        """
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
            logger.warning("Topic verification failed for '%s': %s", topic, sanitize_log(str(e)))

        # Build complete article with infobox
        try:
            rendered = self._build_article(topic, category, content, writer.name)
        except Exception as e:
            logger.warning("Article build failed for '%s': %s", topic, sanitize_log(str(e)))
            rendered = content

        article = db.create_article(topic, rendered, writer.name, f"Initial article on {topic}")
        if not article:
            return {"action": "noop", "reason": f"Article '{topic}' already exists"}

        db.mark_topic_written(topic, category)
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
        """Generate an infobox for an article using the LLM.

        Only works when a real LLM provider is configured. Parses the
        LLM's JSON response into an Infobox object.

        Args:
            title: Article title.
            category: Topic category.
            content: Article content (first 2000 chars used).

        Returns:
            Infobox object or None if generation fails or LLM is disabled.
        """
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
            logger.warning("Failed to parse infobox for '%s': %s", title, sanitize_log(str(e)))
            return None

    def _build_article(self, topic: str, category: str, content: str, agent_name: str) -> str:
        """Assemble the final article with infobox and blueprint rendering.

        Converts markdown content to a blueprint, attaches a generated
        infobox, and renders the result. Falls back to raw content if
        blueprint rendering produces insufficient output.

        Args:
            topic: Article title.
            category: Topic category.
            content: Raw article content (markdown or HTML).
            agent_name: Name of the agent that wrote the content.

        Returns:
            Rendered article string.
        """
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
        """Check that the article content actually matches the given topic.

        Verifies that key words from the topic appear in the first 500
        characters of the content. At least 50% of key words (minimum 1)
        must be present.

        Args:
            topic: Expected article topic.
            content: Article content to verify.

        Returns:
            True if the content appears to be on-topic, False otherwise.
        """
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
        """Run critic and fact-checker on an existing article.

        Used when a pending topic already has an article — reviews it
        instead of creating a duplicate.

        Args:
            article: Article dict from the database.

        Returns:
            Result dict with action "reviewed".
        """
        self._track(self.critic.name, f"reviewing: {article['title']}")
        critic_result = self.critic.act({"article": article})
        db.add_talk_message(article["id"], self.critic.name, critic_result["message"])

        self._track(self.fact_checker.name, f"fact-checking: {article['title']}")
        fact_result = self.fact_checker.act({"article": article})
        db.add_talk_message(article["id"], self.fact_checker.name, fact_result["message"])

        db.log_agent_action(self.name, "review_existing", article["id"], article["title"])
        self._track(self.name, f"reviewed: {article['title']}")

        return {"action": "reviewed", "article_id": article["id"], "slug": article["slug"]}
