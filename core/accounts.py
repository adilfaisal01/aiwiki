"""User account management.

Provides functions for creating, authenticating, and updating user accounts,
including session token handling, avatar and locale updates, and cookie-based
user resolution from HTTP requests.
"""

from __future__ import annotations

import secrets
import uuid

import core.database as db
from core import passwords

ACCOUNT_COOKIE = "aiwiki_account_session"
ACCOUNT_COOKIE_MAX_AGE = 365 * 24 * 60 * 60

_USER_COLUMNS = "id, email, created_at, avatar_url, locale"


def create_user(email: str, password: str) -> dict:
    """Create a new user account with the given email and password.

    Generates a unique user ID, session token, and password hash, then
    inserts the user into the database.

    Args:
        email: The user's email address.
        password: The plaintext password to hash and store.

    Returns:
        A dict with id, email, session_token, created_at, and avatar_url.

    Raises:
        Exception: If the database insert fails (transaction is rolled back).
    """
    user_id = str(uuid.uuid4())
    session_token = secrets.token_urlsafe(32)
    password_hash = passwords.hash_password(password)
    ts = db.now()
    conn = db.get_db()
    p = db._param_style()
    try:
        db._execute(
            conn,
            f"INSERT INTO users (id, session_token, created_at, email, password_hash) "
            f"VALUES ({p}, {p}, {p}, {p}, {p})",
            (user_id, session_token, ts, email, password_hash),
        )
        conn.commit()
        return {
            "id": user_id,
            "email": email,
            "session_token": session_token,
            "created_at": ts,
            "avatar_url": None,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_user_by_session_token(session_token: str) -> dict | None:
    """Look up a user by their session token.

    Args:
        session_token: The session token string from the account cookie.

    Returns:
        A user dict (id, email, created_at, avatar_url, locale) or None.
    """
    if not session_token:
        return None
    conn = db.get_db()
    p = db._param_style()
    row = db._fetchone(
        conn,
        f"SELECT {_USER_COLUMNS} FROM users WHERE session_token = {p}",
        (session_token,),
    )
    conn.close()
    return row


def get_user_by_email(email: str) -> dict | None:
    """Look up a user by their email address.

    Args:
        email: The email address to search for.

    Returns:
        A user dict including password_hash and session_token, or None.
    """
    conn = db.get_db()
    p = db._param_style()
    row = db._fetchone(
        conn,
        f"SELECT id, email, created_at, avatar_url, password_hash, session_token FROM users WHERE email = {p}",
        (email,),
    )
    conn.close()
    return row


def get_user_by_id(user_id: str) -> dict | None:
    """Look up a user by their unique ID.

    Args:
        user_id: The UUID string identifying the user.

    Returns:
        A user dict (id, email, created_at, avatar_url, locale) or None.
    """
    conn = db.get_db()
    p = db._param_style()
    row = db._fetchone(
        conn,
        f"SELECT {_USER_COLUMNS} FROM users WHERE id = {p}",
        (user_id,),
    )
    conn.close()
    return row


def authenticate_user(email: str, password: str) -> dict | None:
    """Verify email and password against the stored credentials.

    Args:
        email: The user's email address.
        password: The plaintext password to verify.

    Returns:
        The full user dict on success, or None if credentials are invalid.
    """
    user = get_user_by_email(email)
    if not user or not user.get("password_hash"):
        return None
    if not passwords.verify_password(password, user["password_hash"]):
        return None
    return user


def email_exists(email: str) -> bool:
    """Check whether an email address is already registered.

    Args:
        email: The email address to check.

    Returns:
        True if a user with that email exists, False otherwise.
    """
    return get_user_by_email(email) is not None


def complete_user_registration(user_id: str, email: str, password: str) -> dict | None:
    """Finalize registration for a pre-created user (e.g. OAuth flow).

    Sets the email and password hash on an existing user record that has a
    null email. Returns None if the email is already taken.

    Args:
        user_id: The UUID of the user to complete.
        email: The email address to set.
        password: The plaintext password to hash and store.

    Returns:
        A user dict with session_token on success, or None on conflict/failure.
    """
    if email_exists(email):
        return None
    conn = db.get_db()
    p = db._param_style()
    password_hash = passwords.hash_password(password)
    try:
        db._execute(
            conn,
            f"UPDATE users SET email = {p}, password_hash = {p} WHERE id = {p} AND email IS NULL",
            (email, password_hash, user_id),
        )
        conn.commit()
        row = db._fetchone(
            conn,
            f"SELECT {_USER_COLUMNS}, session_token FROM users WHERE id = {p}",
            (user_id,),
        )
        if not row or row.get("email") != email:
            return None
        return row
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_user_avatar(user_id: str, avatar_url: str | None) -> dict | None:
    """Update a user's avatar URL.

    Args:
        user_id: The UUID of the user.
        avatar_url: The new avatar URL, or None to clear.

    Returns:
        The updated user dict, or None if the user is not found.
    """
    conn = db.get_db()
    p = db._param_style()
    try:
        db._execute(
            conn,
            f"UPDATE users SET avatar_url = {p} WHERE id = {p}",
            (avatar_url, user_id),
        )
        conn.commit()
        return get_user_by_id(user_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_user_locale(user_id: str, locale: str | None) -> dict | None:
    """Update a user's locale preference.

    Args:
        user_id: The UUID of the user.
        locale: The new locale string (e.g. 'en', 'fr'), or None to clear.

    Returns:
        The updated user dict, or None if the user is not found.
    """
    conn = db.get_db()
    p = db._param_style()
    try:
        db._execute(
            conn,
            f"UPDATE users SET locale = {p} WHERE id = {p}",
            (locale, user_id),
        )
        conn.commit()
        return get_user_by_id(user_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def public_user(user: dict) -> dict:
    """Strip sensitive fields from a user dict for public API responses.

    Args:
        user: The full user dict from the database.

    Returns:
        A safe dict with only id, email, created_at, avatar_url, and locale.
    """
    avatar = (user.get("avatar_url") or "").strip() or None
    locale = (user.get("locale") or "").strip() or None
    return {
        "id": user["id"],
        "email": user.get("email"),
        "created_at": user["created_at"],
        "avatar_url": avatar,
        "locale": locale,
    }


def account_initials(user_id: str) -> str:
    """Derive a 2-character initials string from a user ID.

    Args:
        user_id: The UUID string.

    Returns:
        Two uppercase characters derived from the UUID.
    """
    return user_id.replace("-", "")[:2].upper()


def account_initials_hue(user_id: str) -> int:
    """Compute a deterministic HSL hue (0-359) from a user ID.

    Useful for assigning a consistent colour to a user's avatar placeholder.

    Args:
        user_id: The UUID string.

    Returns:
        An integer hue value between 0 and 359.
    """
    hue = 0
    for char in user_id:
        hue = (hue * 31 + ord(char)) & 0xFFFFFFFF
    return hue % 360


def user_from_request(request) -> dict | None:
    """Resolve the current user from the session cookie in an HTTP request.

    Args:
        request: A FastAPI Request object.

    Returns:
        A user dict if a valid session cookie is present, or None.
    """
    token = request.cookies.get(ACCOUNT_COOKIE)
    return get_user_by_session_token(token.strip() if token else "")
