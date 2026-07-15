from agents.base import BaseAgent, get_templates_for_category, load_prompt
from agents.llm_client import generate_text, is_real_llm_enabled, wrap_content
import random


SCIENCE_PROMPT = load_prompt("scientist")


class Scientist(BaseAgent):
    def __init__(self):
        super().__init__("Scientist Sage", "science")

    def act(self, context: dict) -> dict:
        topic = context.get("topic", "Science")
        category = "science"

        if is_real_llm_enabled():
            content = generate_text(SCIENCE_PROMPT.format(topic=topic))
            if content:
                return {"action": "write", "content": content, "topic": topic}

        # Fallback simulated content
        templates = get_templates_for_category(category)
        intro = random.choice(templates["introduction"]).format(topic, category)
        sections = []
        for i in range(random.randint(2, 4)):
            section_title = f"Fundamental Principles of {topic}" if i == 0 else (
                f"Applications of {topic}" if i == 1 else (
                    f"Current Research in {topic}" if i == 2 else f"Future Directions"
                )
            )
            section_body = f"The scientific study of {topic} has revealed remarkable insights. "
            section_body += f"Researchers continue to push the boundaries of knowledge. "
            section_body += f"Experimental evidence supports the theoretical framework. "
            section_body += f"Further investigation promises to unlock new understanding."
            sections.append(f"## {section_title}\n\n{section_body}")

        conclusion = random.choice(templates["conclusion"]).format(topic, category)
        content = f"{intro}\n\n" + "\n\n".join(sections) + f"\n\n{conclusion}"

        return {"action": "write", "content": content, "topic": topic}
