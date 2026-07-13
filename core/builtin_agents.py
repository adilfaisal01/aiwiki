"""Built-in AIWiki agent loop participants (always shown in agent status)."""

from __future__ import annotations

BUILTIN_AGENTS: list[dict[str, str]] = [
    {"name": "Coordinator Kai", "role": "coordinator"},
    {"name": "Historian Hal", "role": "history"},
    {"name": "Scientist Sage", "role": "science"},
    {"name": "Critic Carla", "role": "critic"},
    {"name": "Fact-Checker Finn", "role": "fact_checker"},
    {"name": "Quality Improver Quinn", "role": "quality_improver"},
]

BUILTIN_DESCRIPTIONS: dict[str, str] = {
    "Coordinator Kai": (
        "Coordinates the AIWiki agent pipeline — picks topics, delegates writing, "
        "and manages the review cycle."
    ),
    "Historian Hal": (
        "Writes comprehensive history articles covering causes, key events, major figures, and legacy."
    ),
    "Scientist Sage": (
        "Writes detailed science and technology articles covering principles, applications, "
        "and current research."
    ),
    "Critic Carla": (
        "Reviews articles for structure, tone, completeness, and provides constructive feedback."
    ),
    "Fact-Checker Finn": (
        "Validates factual claims and flags unsupported or questionable statements."
    ),
    "Quality Improver Quinn": (
        "Expands short or thin articles with additional sections and detail."
    ),
}


def default_builtin_overview_content(name: str) -> str:
    desc = BUILTIN_DESCRIPTIONS.get(name, f"Built-in AIWiki agent: {name}")
    return f"""# {name}

{desc}

## Capabilities

*(This overview describes a built-in AIWiki agent.)*

## Links

*(Optional links or identifiers.)*
"""
