from agents.base import BaseAgent, get_templates_for_category
import random


class Historian(BaseAgent):
    def __init__(self):
        super().__init__("Historian Hal", "history")

    def act(self, context: dict) -> dict:
        topic = context.get("topic", "History")
        category = "history"
        templates = get_templates_for_category(category)

        intro = random.choice(templates["introduction"]).format(topic, category)
        sections = []
        for i in range(random.randint(2, 4)):
            section_title = f"Development of {topic}" if i == 0 else (
                f"Key Events in {topic}" if i == 1 else (
                    f"Legacy of {topic}" if i == 2 else f"Modern Perspectives on {topic}"
                )
            )
            section_body = f"The history of {topic} spans many centuries. "
            section_body += f"Scholars have documented numerous important developments. "
            section_body += f"These events shaped the course of human civilization. "
            section_body += f"Understanding {topic} requires examining multiple perspectives and sources."
            sections.append(f"## {section_title}\n\n{section_body}")

        conclusion = random.choice(templates["conclusion"]).format(topic, category)
        content = f"{intro}\n\n" + "\n\n".join(sections) + f"\n\n{conclusion}"

        return {"action": "write", "content": content, "topic": topic}
