import json
import os
import random
import re
from abc import ABC, abstractmethod
from collections import defaultdict


class BaseAgent(ABC):
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role

    @abstractmethod
    def act(self, context: dict) -> dict:
        ...


class MarkovChain:
    def __init__(self, order: int = 2):
        self.order = order
        self.chain: dict[tuple[str, ...], list[str]] = defaultdict(list)
        self.starts: list[tuple[str, ...]] = []

    def train(self, text: str):
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

_TOPICS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "topics.json")

_FALLBACK_TOPICS: dict[str, list[str]] = {
    "history": [
        "Ancient Civilizations", "The Industrial Revolution", "World War II",
        "The Renaissance", "The Cold War", "Ancient Rome", "The Silk Road",
        "The French Revolution", "The Age of Exploration", "The Ottoman Empire",
    ],
    "science": [
        "Quantum Mechanics", "Evolutionary Biology", "Relativity",
        "Genetics", "Thermodynamics", "Cell Biology", "Plate Tectonics",
        "The Standard Model", "Neuroscience", "Climate Science",
    ],
    "technology": [
        "The Internet", "Machine Learning", "Blockchain",
        "Robotics", "Cryptography", "Cloud Computing", "Computer Vision",
        "Natural Language Processing", "Virtual Reality", "Cybersecurity",
    ],
    "culture": [
        "Jazz Music", "Modern Architecture", "Impressionism",
        "Cinema of the 20th Century", "Street Art", "Japanese Anime",
        "Renaissance Art", "Electronic Music", "Surrealism", "Folk Literature",
    ],
}


def _load_topics() -> dict[str, list[str]]:
    try:
        with open(_TOPICS_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, dict) and all(isinstance(v, list) for v in data.values()):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return dict(_FALLBACK_TOPICS)


def _save_topics(topics: dict[str, list[str]]):
    try:
        os.makedirs(os.path.dirname(_TOPICS_FILE), exist_ok=True)
        with open(_TOPICS_FILE, "w") as f:
            json.dump(topics, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def append_topics(new_topics: list[tuple[str, str]]):
    topics = _load_topics()
    changed = False
    for topic, category in new_topics:
        if category not in topics:
            topics[category] = []
        if topic not in topics[category]:
            topics[category].append(topic)
            changed = True
    if changed:
        _save_topics(topics)


def get_templates_for_category(category: str) -> dict[str, list[str]]:
    return TEMPLATES


def get_topics_for_category(category: str) -> list[str]:
    topics = _load_topics()
    return topics.get(category, topics.get("science", []))


def pick_topic(category: str | None = None, exclude_slugs: set[str] | None = None) -> tuple[str, str]:
    topics = _load_topics()
    if not topics:
        topics = dict(_FALLBACK_TOPICS)
    if category and category in topics:
        candidates = [t for t in topics[category] if not exclude_slugs or _slug_for_topic(t) not in exclude_slugs]
        if candidates:
            return random.choice(candidates), category
    all_candidates = []
    for cat, ts in topics.items():
        for t in ts:
            if not exclude_slugs or _slug_for_topic(t) not in exclude_slugs:
                all_candidates.append((t, cat))
    if all_candidates:
        return random.choice(all_candidates)
    cat = random.choice(list(_FALLBACK_TOPICS.keys()))
    return random.choice(_FALLBACK_TOPICS[cat]), cat


def _slug_for_topic(topic: str) -> str:
    s = topic.lower().strip()
    s = "".join(c if c.isalnum() or c in " -_" else "" for c in s)
    s = s.replace(" ", "_").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def category_for_writer(category: str) -> str:
    """Map topic category to writer specialization."""
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
    """
    path = os.path.join(_PROMPTS_DIR, f"{name}.md")
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def validate_prompts() -> list[str]:
    """Check all prompt files have the expected format keys.

    Returns a list of error messages (empty if all valid).
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
