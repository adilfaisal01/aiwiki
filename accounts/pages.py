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
)

SETTINGS_NAV_SECTIONS = (
    {"id": "account-preferences", "label_key": "nav.section.preferences"},
    {"id": "account-apis", "label_key": "nav.section.apis"},
)


def _localized_nav_sections(locale: str, sections: tuple[dict[str, str], ...]) -> tuple[dict[str, str], ...]:
    return tuple(
        {"id": section["id"], "label": t(locale, section["label_key"])}
        for section in sections
    )


def _account_page_redirect(user: dict | None) -> RedirectResponse | None:
    if not user:
        return RedirectResponse("/account/login", status_code=303)
    if not user.get("email"):
        return RedirectResponse("/account/login?mode=register", status_code=303)
    return None


@router.get("/account/login", response_class=HTMLResponse)
async def account_login_page(request: Request):
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
