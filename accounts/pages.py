"""Account page routes (HTML responses).

Provides server-rendered HTML pages for account login, profile,
and settings management.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core import accounts
from core import config
from web.i18n import t
from web.template_env import render_template

router = APIRouter(tags=["account-pages"])

ACCOUNT_NAV_SECTIONS = (
    {"id": "account-profile", "label_key": "nav.section.profile"},
    {"id": "account-avatar", "label_key": "nav.section.avatar"},
    {"id": "account-id", "label_key": "nav.section.account_id"},
    {"id": "account-usage", "label_key": "nav.section.usage"},
)

SETTINGS_NAV_SECTIONS = (
    {"id": "account-preferences", "label_key": "nav.section.preferences"},
    {"id": "account-apis", "label_key": "nav.section.apis"},
)


def _localized_nav_sections(locale: str, sections: tuple[dict[str, str], ...]) -> tuple[dict[str, str], ...]:
    """Translate navigation section labels for the given locale.

    Args:
        locale: Target locale string (e.g. "en", "fr").
        sections: Tuple of section dicts with "id" and "label_key" keys.

    Returns:
        Tuple of section dicts with "id" and translated "label".
    """
    return tuple(
        {"id": section["id"], "label": t(locale, section["label_key"])}
        for section in sections
    )


def _account_page_redirect(user: dict | None) -> RedirectResponse | None:
    """Redirect unauthenticated or email-less users to the login page.

    Args:
        user: The current user dict, or None if not authenticated.

    Returns:
        A RedirectResponse to /account/login if the user is missing or
        has no email, otherwise None.
    """
    if not user:
        return RedirectResponse("/account/login", status_code=303)
    if not user.get("email"):
        return RedirectResponse("/account/login?mode=register", status_code=303)
    return None


@router.get("/account/login", response_class=HTMLResponse)
async def account_login_page(request: Request):
    """Render the account login/registration page.

    Redirects authenticated users to /account.

    Args:
        request: The incoming HTTP request.

    Returns:
        HTML response with the login template.
    """
    user = accounts.user_from_request(request)
    if user and user.get("email"):
        return RedirectResponse("/account", status_code=303)
    return render_template(
        request,
        "account_login.html",
        {"avatar_upload_enabled": config.AVATAR_UPLOAD_ENABLED},
    )


@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    """Render the account profile page.

    Redirects unauthenticated users to the login page.

    Args:
        request: The incoming HTTP request.

    Returns:
        HTML response with the account profile template.
    """
    user = accounts.user_from_request(request)
    redirect = _account_page_redirect(user)
    if redirect:
        return redirect
    locale = request.state.locale
    return render_template(
        request,
        "account.html",
        {
            "user": accounts.public_user(user),
            "avatar_upload_enabled": config.AVATAR_UPLOAD_ENABLED,
            "active_page": "account",
            "nav_sections": _localized_nav_sections(locale, ACCOUNT_NAV_SECTIONS),
        },
    )


@router.get("/account/settings", response_class=HTMLResponse)
async def account_settings_page(request: Request):
    """Render the account settings/preferences page.

    Redirects unauthenticated users to the login page.

    Args:
        request: The incoming HTTP request.

    Returns:
        HTML response with the account preferences template.
    """
    user = accounts.user_from_request(request)
    redirect = _account_page_redirect(user)
    if redirect:
        return redirect
    locale = request.state.locale
    return render_template(
        request,
        "account_preferences.html",
        {
            "user": accounts.public_user(user),
            "active_page": "settings",
            "nav_sections": _localized_nav_sections(locale, SETTINGS_NAV_SECTIONS),
        },
    )
