"""Base agent classes, Markov chain text generation, and prompt utilities.

Defines the abstract BaseAgent interface, a MarkovChain for simulated
content generation, template-based article scaffolding, and functions
for loading and validating agent prompt files.
"""

import os
import random
import re
from abc import ABC, abstractmethod
from collections import defaultdict

import core.database as db


class BaseAgent(ABC):
    """Abstract base class for all AIWiki agents.

    Every agent has a name and role, and must implement the act() method
    which receives a context dictionary and returns a result dictionary.
    """

    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role

    @abstractmethod
    def act(self, context: dict) -> dict:
        """Execute the agent's primary action.

        Args:
            context: Dictionary containing input data for the agent
                     (e.g. topic, article, feedback).

        Returns:
            A dictionary with at minimum an "action" key describing
            what was performed.
        """
        ...


class MarkovChain:
    """An order-n Markov chain for generating simulated article text.

    Trained on existing text, it learns transition probabilities between
    word sequences and can produce new text of a requested length.
    """

    def __init__(self, order: int = 2):
        """Initialize the Markov chain.

        Args:
            order: Number of preceding words used to predict the next word.
        """
        self.order = order
        self.chain: dict[tuple[str, ...], list[str]] = defaultdict(list)
        self.starts: list[tuple[str, ...]] = []

    def train(self, text: str):
        """Train the chain on a body of text.

        Args:
            text: Raw text to learn word transition patterns from.
        """
        words = re.findall(r"\S+|\n", text)
        if len(words) < self.order + 1:
            return
        for i in range(len(words) - self.order):
            key = tuple(words[i : i + self.order])
            next_word = words[i + self.order]
            self.chain[key].append(next_word)
            if i == 0 or words[i - 1] == "\n":
                self.starts.append(key)

    def generate(self, min_words: int = 50, max_words: int = 200) -> str:
        """Generate text from the trained chain.

        Args:
            min_words: Minimum number of words before stopping at a
                       sentence boundary.
            max_words: Hard limit on generated word count.

        Returns:
            Generated text string, or empty string if chain is untrained.
        """
        if not self.chain:
            return ""
        key = random.choice(self.starts) if self.starts else random.choice(list(self.chain.keys()))
        output = list(key)
        for _ in range(max_words):
            if key in self.chain:
                next_word = random.choice(self.chain[key])
                output.append(next_word)
                key = tuple(output[-self.order :])
                if len(output) >= min_words and next_word.endswith((".", "!", "?")):
                    break
            else:
                break
        return " ".join(output)


TEMPLATES: dict[str, list[str]] = {
    "introduction": [
        "{} is a significant topic in {} that has shaped our understanding of the world.",
        "The study of {} encompasses a wide range of phenomena and ideas within {}.",
        "{} represents one of the most important developments in the field of {}.",
        "Since its emergence, {} has fundamentally transformed the landscape of {}.",
    ],
    "section": [
        "## {}\n\n{}",
        "## {}\n\nThe concept of {} has been explored extensively. {}",
        "## {}\n\n{} represents a key area of investigation. {}",
    ],
    "conclusion": [
        "In summary, {} continues to evolve and influence {} in profound ways.",
        "The ongoing research into {} promises to yield further insights into {}.",
        "As our understanding of {} deepens, its impact on {} will likely grow.",
    ],
}


def get_templates_for_category(category: str) -> dict[str, list[str]]:
    """Return article-writing templates for a given category.

    Currently returns the same global TEMPLATES dict regardless of
    category. Exists as a seam for future category-specific templates.

    Args:
        category: Topic category (e.g. "history", "science").

    Returns:
        Dictionary of template lists keyed by section type.
    """
    return TEMPLATES


def pick_topic(category: str | None = None, exclude_slugs: set[str] | None = None) -> tuple[str, str]:
    """Select an unwritten topic from the database.

    Delegates to core.database.pick_topic.

    Args:
        category: Optional category filter (None = any category).
        exclude_slugs: Set of slugs to exclude (already-written articles).

    Returns:
        Tuple of (topic_name, category).
    """
    return db.pick_topic(category=category, exclude_slugs=exclude_slugs)


def append_topics(new_topics: list[tuple[str, str]]):
    """Add new topics (e.g. from See also links) to the topic pool.

    Args:
        new_topics: List of (topic_name, category) tuples to add.
    """
    db.append_topics(new_topics)


def category_for_writer(category: str) -> str:
    """Map a topic category to the writer specialization that handles it.

    Args:
        category: Topic category string.

    Returns:
        "history" for history/culture topics, "science" for all others.
    """
    if category in ("history", "culture"):
        return "history"
    return "science"


_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

# Expected format keys for each prompt file
_PROMPT_KEYS: dict[str, set[str]] = {
    "historian": {"topic"},
    "scientist": {"topic"},
    "critic": {"topic", "content"},
    "fact_checker": {"topic", "content"},
    "quality_improver": {"topic", "content", "feedback"},
    "infobox_generate": {"title", "category", "content"},
}


def load_prompt(name: str) -> str:
    """Load an agent prompt from the prompts/ directory.

    Prompts are stored as .md files in agents/prompts/ so they can be
    edited independently of the Python code. Code changes (migrations,
    bug fixes, etc.) won't accidentally modify agent behavior.

    Args:
        name: Prompt file name (without .md extension).

    Returns:
        Prompt text string, or empty string if file not found.
    """
    path = os.path.join(_PROMPTS_DIR, f"{name}.md")
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def validate_prompts() -> list[str]:
    """Check all prompt files have the expected format keys.

    Iterates over _PROMPT_KEYS, loads each prompt file, and verifies
    that all required {key} placeholders are present. Also flags any
    unexpected keys.

    Returns:
        List of error messages. Empty list if all prompts are valid.
    """
    errors = []
    for name, expected_keys in _PROMPT_KEYS.items():
        prompt = load_prompt(name)
        if not prompt:
            errors.append(f"Prompt file '{name}.md' not found or empty")
            continue
        found = set()
        for match in re.finditer(r"\{(\w+)\}", prompt):
            found.add(match.group(1))
        missing = expected_keys - found
        if missing:
            errors.append(
                f"Prompt '{name}.md' missing format keys: {', '.join(sorted(missing))}"
            )
        extra = found - expected_keys - {"p", "q1", "q2"}
        if extra:
            errors.append(
                f"Prompt '{name}.md' has unexpected format keys: {', '.join(sorted(extra))} "
                f"(update _PROMPT_KEYS in base.py if intentional)"
            )
    return errors
