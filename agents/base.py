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

TOPICS: dict[str, list[str]] = {
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


def get_templates_for_category(category: str) -> dict[str, list[str]]:
    return TEMPLATES


def get_topics_for_category(category: str) -> list[str]:
    return TOPICS.get(category, TOPICS["science"])


def pick_topic(category: str | None = None) -> tuple[str, str]:
    if category and category in TOPICS:
        topic = random.choice(TOPICS[category])
        return topic, category
    cat = random.choice(list(TOPICS.keys()))
    topic = random.choice(TOPICS[cat])
    return topic, cat


def category_for_writer(category: str) -> str:
    """Map topic category to writer specialization."""
    if category == "history":
        return "history"
    if category in ("science", "technology"):
        return "science"
    return "culture"
