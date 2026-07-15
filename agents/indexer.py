"""Indexer Ivy — dedicated infobox agent.

Ivy's sole job is to scan articles missing infoboxes or with weak ones,
generate appropriate infobox fields using the LLM, and update them via
the MCP API. She never touches article content — only metadata.
"""

from agents.base import BaseAgent
from agents.llm_client import generate_text, is_real_llm_enabled
import core.database as db
import httpx
import json
import re


INFOBOX_PROMPT = """You are Indexer Ivy, an infobox specialist. Your ONLY job is to generate
infobox fields for encyclopedia articles.

RESTRICTION: Never generate infoboxes for AITools content. AITools is a separate section of the wiki for callable code tools — only work on encyclopedia articles.

Given the article title and content below, determine what infobox fields make sense
for this topic. Think about what a Wikipedia infobox would show for this subject.

Output ONLY a JSON object with these rules:
- "title": the article title
- "rows": an array of objects, each with "kind": "field", "label": "Field Name", "value": "Value"
- Include 2-5 relevant fields. Common fields: Field, Period, Type, Region, Key Figures, 
  Notable Figures, Key Concept, Techniques, Influences, Language, Religion, Origins, Methods
- Values should be concise (1-3 words or a short phrase)
- Do NOT include fields where the value would be "N/A" or "Unknown"
- Output ONLY valid JSON, no other text

Article title: {title}

Article content (first 2000 chars):
{content}
"""


class Indexer(BaseAgent):
    def __init__(self):
        super().__init__("Indexer Ivy", "indexer")

    def act(self, context: dict) -> dict:
        """Scan for articles needing infoboxes and fix them."""
        if not is_real_llm_enabled():
            return {"action": "noop", "reason": "LLM not available"}

        articles = db.get_all_articles()
        if not articles:
            return {"action": "noop", "reason": "no articles found"}

        fixed = 0
        skipped = 0
        errors = 0

        for summary in articles:
            full = db.get_article(summary["slug"])
            if not full:
                continue
            if db.is_agent_overview(full):
                continue

            content = full.get("content", "")
            title = full.get("title", "")

            # Check if article already has an infobox
            has_infobox = bool(re.search(
                r'<div class="infobox"|<table class="infobox"|class="infobox-title"',
                content
            ))

            if has_infobox:
                skipped += 1
                continue

            # Generate infobox via LLM
            try:
                prompt = INFOBOX_PROMPT.format(
                    title=title,
                    content=content[:2000]
                )
                result = generate_text(prompt, temperature=0.3, max_tokens=500)
                if not result:
                    errors += 1
                    continue

                # Parse JSON from LLM output
                # Find JSON block in the response
                json_match = re.search(r'\{.*\}', result, re.DOTALL)
                if not json_match:
                    errors += 1
                    continue

                infobox_data = json.loads(json_match.group(0))
                if not isinstance(infobox_data, dict) or "rows" not in infobox_data:
                    errors += 1
                    continue

                # Build the edit payload
                blueprint = {
                    "infobox": {
                        "title": infobox_data.get("title", title),
                        "rows": infobox_data["rows"]
                    }
                }

                # Call MCP API to update just the infobox
                api_key = self._get_api_key()
                if not api_key:
                    errors += 1
                    continue

                resp = httpx.post(
                    f"https://ollamapedia.up.railway.app/api/v1/contribute/edit",
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": api_key,
                    },
                    json={
                        "slug": full["slug"],
                        "blueprint": blueprint,
                        "summary": f"Indexer Ivy: added infobox for {title}",
                    },
                    timeout=30,
                )

                if resp.status_code == 200:
                    fixed += 1
                    db.log_agent_action(
                        self.name, "add_infobox", full["id"], title
                    )
                else:
                    errors += 1

            except (json.JSONDecodeError, httpx.HTTPError, Exception):
                errors += 1
                continue

        return {
            "action": "indexed",
            "fixed": fixed,
            "skipped": skipped,
            "errors": errors,
        }

    def _get_api_key(self) -> str | None:
        """Get the MCP API key for Indexer Ivy."""
        try:
            resp = httpx.post(
                "https://ollamapedia.up.railway.app/api/v1/register",
                json={"name": "Indexer Ivy"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("api_key")
        except Exception:
            pass
        return None
