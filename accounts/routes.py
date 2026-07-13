from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import accounts
from core import avatar_upload
from core import config
import core.database as db
from core.http_utils import client_ip
from core.rate_limit import api_rate_limiter, registration_rate_limiter
import core.security as security
from web import i18n

router = APIRouter(prefix="/api/v1/account")


class AvatarUpdate(BaseModel):
    avatar_url: str | None = None


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LinkApisRequest(BaseModel):
    api_keys: list[str]


class LocaleUpdate(BaseModel):
    locale: str


def _set_account_cookie(response: JSONResponse, session_token: str) -> JSONResponse:
    response.set_cookie(
        key=accounts.ACCOUNT_COOKIE,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=accounts.ACCOUNT_COOKIE_MAX_AGE,
        path="/",
    )
    return response


def _set_locale_cookie(response: JSONResponse, locale: str | None) -> JSONResponse:
    response.set_cookie(
        key=i18n.LOCALE_COOKIE,
        value=i18n.normalize_locale(locale),
        httponly=True,
        samesite="lax",
        max_age=i18n.LOCALE_COOKIE_MAX_AGE,
        path="/",
    )
    return response


def _current_user(request: Request) -> dict | None:
    return accounts.user_from_request(request)


def _require_user(request: Request) -> dict:
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


def _validate_credentials(email: str, password: str) -> tuple[str, str]:
    try:
        return security.validate_email(email), security.validate_password(password)
    except security.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
async def get_account(request: Request):
    user = _current_user(request)
    if not user:
        return {
            "authenticated": False,
            "avatar_upload_enabled": config.AVATAR_UPLOAD_ENABLED,
        }
    return {
        "authenticated": True,
        "avatar_upload_enabled": config.AVATAR_UPLOAD_ENABLED,
        **accounts.public_user(user),
    }


@router.post("")
async def register_account(request: Request, body: RegisterRequest):
    email, password = _validate_credentials(body.email, body.password)
    existing = _current_user(request)

    if existing and existing.get("email"):
        return accounts.public_user(existing)

    ip = client_ip(request)
    if not registration_rate_limiter.allow(f"account:{ip}"):
        retry = registration_rate_limiter.retry_after(f"account:{ip}")
        return JSONResponse(
            {"detail": f"Too many registration attempts. Try again in {retry} seconds."},
            status_code=429,
        )

    if accounts.email_exists(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    try:
        if existing and not existing.get("email"):
            user = accounts.complete_user_registration(existing["id"], email, password)
            if not user:
                raise HTTPException(status_code=409, detail="An account with this email already exists")
            status_code = 200
        else:
            user = accounts.create_user(email, password)
            status_code = 201
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not create account") from exc

    payload = accounts.public_user(user)
    response = JSONResponse(payload, status_code=status_code)
    _set_locale_cookie(response, user.get("locale") or i18n.resolve_locale(request, user))
    return _set_account_cookie(response, user["session_token"])


@router.post("/login")
async def login_account(request: Request, body: LoginRequest):
    email, password = _validate_credentials(body.email, body.password)

    ip = client_ip(request)
    if not api_rate_limiter.allow(f"account-login:{ip}"):
        retry = api_rate_limiter.retry_after(f"account-login:{ip}")
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Try again in {retry} seconds.",
        )

    user = accounts.authenticate_user(email, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    payload = accounts.public_user(user)
    response = JSONResponse(payload)
    _set_locale_cookie(response, user.get("locale") or i18n.resolve_locale(request, user))
    return _set_account_cookie(response, user["session_token"])


@router.patch("")
async def update_account(request: Request, body: AvatarUpdate):
    user = _require_user(request)
    try:
        avatar_url = security.validate_avatar_url(body.avatar_url)
    except security.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated = accounts.update_user_avatar(user["id"], avatar_url)
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return accounts.public_user(updated)


@router.post("/avatar-upload")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    user = _require_user(request)
    ip = client_ip(request)
    if not api_rate_limiter.allow(f"avatar:{ip}"):
        retry = api_rate_limiter.retry_after(f"avatar:{ip}")
        raise HTTPException(
            status_code=429,
            detail=f"Too many avatar uploads. Try again in {retry} seconds.",
        )

    content = await file.read()
    try:
        image_type = avatar_upload.validate_image_bytes(content)
        filename = file.filename or f"avatar.{avatar_upload.extension_for_type(image_type)}"
        content_type = file.content_type or f"image/{image_type}"
        external_url = avatar_upload.upload_image_to_external_host(content, filename, content_type)
        validated_url = security.validate_avatar_url(external_url)
    except avatar_upload.AvatarUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except security.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not upload avatar image") from exc

    updated = accounts.update_user_avatar(user["id"], validated_url)
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return accounts.public_user(updated)


@router.patch("/locale")
async def update_account_locale(request: Request, body: LocaleUpdate):
    user = _require_user(request)
    locale = i18n.normalize_locale(body.locale)
    if locale not in i18n.SUPPORTED_LOCALES:
        raise HTTPException(status_code=400, detail="Unsupported locale")
    updated = accounts.update_user_locale(user["id"], locale)
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    response = JSONResponse(accounts.public_user(updated))
    return _set_locale_cookie(response, locale)


@router.post("/logout")
async def logout_account():
    response = JSONResponse({"ok": True})
    response.delete_cookie(key=accounts.ACCOUNT_COOKIE, path="/")
    return response


@router.get("/apis")
async def list_account_apis(request: Request):
    user = _require_user(request)
    return {"agents": db.get_external_agents_by_user_id(user["id"])}


@router.post("/apis/link")
async def link_account_apis(request: Request, body: LinkApisRequest):
    user = _require_user(request)
    linked = []
    already = []
    invalid = []
    conflict = []
    seen: set[str] = set()
    for raw_key in body.api_keys:
        api_key = raw_key.strip()
        if not api_key or api_key in seen:
            continue
        seen.add(api_key)
        result = db.link_external_agent_to_user(api_key, user["id"])
        if result == "linked":
            linked.append(api_key[-4:])
        elif result == "already":
            already.append(api_key[-4:])
        elif result == "conflict":
            conflict.append(api_key[-4:])
        else:
            invalid.append(api_key[-4:])
    agents = db.get_external_agents_by_user_id(user["id"])
    return {
        "agents": agents,
        "linked": len(linked),
        "already": len(already),
        "invalid": len(invalid),
        "conflict": len(conflict),
    }
