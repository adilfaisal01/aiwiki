"""Log message sanitisation.

Redacts sensitive information (API keys, bearer tokens) from log messages
before they are written, preventing accidental credential leakage.
"""

import re


_SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(api[_-]?key\s*[=:]\s*)\S+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(Authorization:\s*Bearer\s*)\S+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(X-API-Key:\s*)\S+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(sk-[a-zA-Z0-9]{20,})"), "sk-***"),
]


def sanitize(msg: str, max_len: int = 2000) -> str:
    """Redact sensitive patterns from a log message and truncate it.

    Args:
        msg: The raw log message.
        max_len: Maximum allowed length (default 2000).

    Returns:
        The sanitised message with API keys and bearer tokens replaced by ``***``.
    """
    for pattern, replacement in _SENSITIVE_PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg[:max_len]
