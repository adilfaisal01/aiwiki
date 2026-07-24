"""Internationalization (i18n) support for AIWiki.

Loads JSON translation catalogs from the locales directory and provides
locale resolution, message translation with variable interpolation,
and client-side configuration serialization.
"""

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
    """Load the translation catalog for a locale, caching it in memory.

    Args:
        locale: The locale string to load (e.g. "en", "fr").

    Returns:
        A dictionary mapping translation keys to translated strings.
    """
    normalized = normalize_locale(locale)
    if normalized not in _catalogs:
        path = LOCALE_DIR / f"{normalized}.json"
        with path.open(encoding="utf-8") as handle:
            _catalogs[normalized] = json.load(handle)
    return _catalogs[normalized]


def parse_locale(value: str | None) -> str | None:
    """Parse and validate a locale string against supported locales.

    Accepts formats like "en", "en-US", "en_US". Returns the primary
    language subtag if supported, or None for unsupported locales.

    Args:
        value: The raw locale string to parse.

    Returns:
        A supported locale string, or None if the input is empty or unsupported.
    """
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
    """Parse a locale and fall back to the default if unsupported.

    Args:
        value: The raw locale string to normalize.

    Returns:
        A supported locale string, guaranteed to be non-None.
    """
    return parse_locale(value) or DEFAULT_LOCALE


def t(locale: str, key: str, **kwargs: object) -> str:
    """Translate a key into the given locale with optional variable interpolation.

    Falls back to the default locale's catalog if the key is missing,
    then to the raw key itself.

    Args:
        locale: The target locale.
        key: The translation key.
        **kwargs: Variable substitutions for ``{name}`` placeholders.

    Returns:
        The translated string with variables replaced.
    """
    normalized = normalize_locale(locale)
    catalog = _load_catalog(normalized)
    fallback = _load_catalog(DEFAULT_LOCALE)
    text = catalog.get(key) or fallback.get(key) or key
    for name, value in kwargs.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def client_messages(locale: str) -> dict[str, str]:
    """Return the full translation catalog for a locale as a flat dict.

    Args:
        locale: The target locale.

    Returns:
        A dictionary of all translation key-value pairs for the locale.
    """
    return dict(_load_catalog(normalize_locale(locale)))


def client_config_json(locale: str) -> str:
    """Serialize the i18n client configuration as a compact JSON string.

    Includes the resolved locale, default locale, supported locales list,
    and all translated messages.

    Args:
        locale: The target locale.

    Returns:
        A JSON string with the client i18n configuration.
    """
    normalized = normalize_locale(locale)
    payload = {
        "locale": normalized,
        "defaultLocale": DEFAULT_LOCALE,
        "supportedLocales": list(SUPPORTED_LOCALES),
        "messages": client_messages(normalized),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def resolve_locale(request, user: dict | None = None) -> str:
    """Determine the best locale for a request using user, cookie, or Accept-Language.

    Priority order: user account locale > cookie > Accept-Language header > default.

    Args:
        request: The incoming HTTP request (Starlette/FastAPI Request).
        user: Optional authenticated user dict with a ``locale`` key.

    Returns:
        A supported locale string.
    """
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
