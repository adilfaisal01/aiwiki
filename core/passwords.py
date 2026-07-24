"""Password hashing and verification using PBKDF2-SHA256.

Stored format: ``pbkdf2_sha256$iterations$salt_hex$digest_hex``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """Hash a plaintext password with a random salt using PBKDF2-SHA256.

    Args:
        password: The plaintext password.

    Returns:
        The encoded hash string in the format
        ``pbkdf2_sha256$iterations$salt_hex$digest_hex``.
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a plaintext password against a stored hash.

    Args:
        password: The plaintext password to check.
        stored: The stored hash string in ``pbkdf2_sha256$...`` format.

    Returns:
        True if the password matches, False otherwise.
    """
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False
