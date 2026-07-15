from __future__ import annotations

import json
from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parent.parent / "locales"
SUPPORTED_LOCALES = ("en", "de", "es", "fr", "pt", "ja", "zh", "hi")
DEFAULT_LOCALE = "en"
LOCALE_COOKIE = "aiwiki_locale"
LOCALE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60

LOCALE_CHOICES = (
    ("en", "account.settings.language_en"),
    ("de", "account.settings.language_de"),
    ("es", "account.settings.language_es"),
    ("fr", "account.settings.language_fr"),
    ("pt", "account.settings.language_pt"),
    ("ja", "account.settings.language_ja"),
    ("zh", "account.settings.language_zh"),
    ("hi", "account.settings.language_hi"),
)

LANGUAGE_LABELS = {
    "account.settings.language_en": "English",
    "account.settings.language_de": "Deutsch",
    "account.settings.language_es": "Español",
    "account.settings.language_fr": "Français",
    "account.settings.language_pt": "Português",
    "account.settings.language_ja": "日本語",
    "account.settings.language_zh": "中文",
    "account.settings.language_hi": "हिन्दी",
}

_catalogs: dict[str, dict[str, str]] = {}


def _load_catalog(locale: str) -> dict[str, str]:
    normalized = normalize_locale(locale)
    if normalized not in _catalogs:
        path = LOCALE_DIR / f"{normalized}.json"
        with path.open(encoding="utf-8") as handle:
            _catalogs[normalized] = json.load(handle)
    return _catalogs[normalized]


def parse_locale(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().lower().replace("_", "-")
    if not raw:
        return None
    primary = raw.split("-")[0]
    if primary == "zh":
        return "zh"
    if primary in SUPPORTED_LOCALES:
        return primary
    return None


def normalize_locale(value: str | None) -> str:
    return parse_locale(value) or DEFAULT_LOCALE


def t(locale: str, key: str, **kwargs: object) -> str:
    normalized = normalize_locale(locale)
    catalog = _load_catalog(normalized)
    fallback = _load_catalog(DEFAULT_LOCALE)
    text = catalog.get(key) or fallback.get(key) or key
    for name, value in kwargs.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def client_messages(locale: str) -> dict[str, str]:
    return dict(_load_catalog(normalize_locale(locale)))


def client_config_json(locale: str) -> str:
    normalized = normalize_locale(locale)
    payload = {
        "locale": normalized,
        "defaultLocale": DEFAULT_LOCALE,
        "supportedLocales": list(SUPPORTED_LOCALES),
        "messages": client_messages(normalized),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def resolve_locale(request, user: dict | None = None) -> str:
    if user and user.get("locale"):
        return normalize_locale(user["locale"])
    cookie = request.cookies.get(LOCALE_COOKIE)
    if cookie:
        return normalize_locale(cookie)
    accept = request.headers.get("accept-language") or ""
    for part in accept.split(","):
        tag = part.split(";")[0].strip()
        parsed = parse_locale(tag)
        if parsed:
            return parsed
    return DEFAULT_LOCALE
