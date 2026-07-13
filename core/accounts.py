from __future__ import annotations

import secrets
import uuid

import core.database as db
from core import passwords

ACCOUNT_COOKIE = "aiwiki_account_session"
ACCOUNT_COOKIE_MAX_AGE = 365 * 24 * 60 * 60

_USER_COLUMNS = "id, email, created_at, avatar_url, locale"


def create_user(email: str, password: str) -> dict:
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
    user = get_user_by_email(email)
    if not user or not user.get("password_hash"):
        return None
    if not passwords.verify_password(password, user["password_hash"]):
        return None
    return user


def email_exists(email: str) -> bool:
    return get_user_by_email(email) is not None


def complete_user_registration(user_id: str, email: str, password: str) -> dict | None:
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
    return user_id.replace("-", "")[:2].upper()


def account_initials_hue(user_id: str) -> int:
    hue = 0
    for char in user_id:
        hue = (hue * 31 + ord(char)) & 0xFFFFFFFF
    return hue % 360


def user_from_request(request) -> dict | None:
    token = request.cookies.get(ACCOUNT_COOKIE)
    return get_user_by_session_token(token.strip() if token else "")
