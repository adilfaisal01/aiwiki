"""Quality improver agent — expands and enhances existing articles.

Rewrites thin articles (under 600 words / 4 sections) and addresses
unresolved feedback from the critic and fact-checker agents. Uses the
LLM when available, with a simulated fallback.
"""

from agents.base import BaseAgent, get_templates_for_category, load_prompt
from agents.llm_client import generate_text, is_real_llm_enabled, wrap_content
import core.database as db


IMPROVE_PROMPT = load_prompt("quality_improver")


class QualityImprover(BaseAgent):
    """Expands and enhances existing articles.

    Rewrites articles that are too short or have unresolved feedback.
    Delegates to the historian or scientist for simulated improvements
    when no LLM is available.
    """

    def __init__(self, historian=None, scientist=None):
        """Initialize the quality improver.

        Args:
            historian: Historian agent instance (for simulated improvements).
            scientist: Scientist agent instance (for simulated improvements).
        """
        super().__init__("Quality Improver Quinn", "quality_improver")
        self.historian = historian
        self.scientist = scientist

    def act(self, context: dict) -> dict:
        """Improve an article by expanding content or addressing feedback.

        Args:
            context: Dict with keys "article" (required) and "feedback"
                     (optional feedback text to address).

        Returns:
            Dict with action "improved" or "noop".
        """
        article = context.get("article")
        if not article:
            return {"action": "noop", "reason": "no article to improve"}

        db.update_agent_activity(self.name, "improve_article")
        topic = article["title"]
        content = article["content"]
        feedback = context.get("feedback", "")

        word_count = len(content.split())
        section_count = content.count("## ")

        if word_count >= 600 and section_count >= 4 and not feedback:
            return {"action": "noop", "reason": "article already meets quality bar"}

        if is_real_llm_enabled():
            prompt = IMPROVE_PROMPT.format(topic=topic, content=wrap_content(content), feedback=feedback or "No specific feedback provided.")
            new_content = generate_text(prompt)
        else:
            new_content = self._simulate_improve(topic, content)

        if not new_content or len(new_content.split()) < 300:
            return {"action": "noop", "reason": "did not produce improved content"}

        if len(new_content.split()) <= word_count:
            return {"action": "noop", "reason": "improved content not longer than original"}

        db.update_article(
            article_id=article["id"],
            content=new_content,
            agent_name=self.name,
            summary=f"Quality improvement rewrite ({word_count} → {len(new_content.split())} words)",
        )
        db.log_agent_action(self.name, "improve_article", article["id"], topic)

        return {"action": "improved", "article_id": article["id"], "slug": article["slug"], "topic": topic}

    def _simulate_improve(self, topic: str, content: str) -> str:
        """Simulate article improvement using writer agents.

        Selects the appropriate writer based on content keywords and
        appends their draft to the original content.

        Args:
            topic: Article topic.
            content: Original article content.

        Returns:
            Expanded content string.
        """
        writer = self.historian if "history" in content.lower() or "century" in content.lower() else self.scientist
        draft = writer.act({"topic": topic})
        expanded = draft.get("content", "")
        if not expanded:
            templates = get_templates_for_category("science")
            sections = []
            for title in ("Background", "Development", "Impact", "See also"):
                body = (
                    f"Researchers continue to study {topic} from multiple angles. "
                    f"Historical records and contemporary analysis provide context for understanding its role."
                )
                sections.append(f"## {title}\n\n{body}")
            expanded = f"{content}\n\n" + "\n\n".join(sections)
        elif content.strip() and content.strip() not in expanded:
            expanded = f"{content}\n\n{expanded}"
        return expanded
