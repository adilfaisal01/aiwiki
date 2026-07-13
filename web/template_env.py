from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from markupsafe import Markup
from starlette.requests import Request

from core import config
from core import accounts
from web.static_assets import static_url
from web.theme_manager import client_config_json, theme_css_url
from web.i18n import (
    LOCALE_CHOICES,
    client_config_json as i18n_client_config_json,
    normalize_locale,
    t,
)
from wiki.code_blocks import normalize_language, pygments_css_url, render_code_block

templates = Jinja2Templates(directory="templates")
templates.env.globals["wiki_edit_enabled"] = config.WIKI_EDIT_ENABLED
templates.env.globals["aitools_enabled"] = config.AITOOLS_ENABLED
templates.env.globals["static_url"] = static_url
templates.env.globals["public_base_url"] = config.PUBLIC_BASE_URL.rstrip("/")
templates.env.globals["app_version"] = config.APP_VERSION
templates.env.globals["donation_url"] = config.DONATION_URL
templates.env.globals["theme_css_url"] = theme_css_url
templates.env.globals["pygments_css_url"] = pygments_css_url
templates.env.globals["theme_client_config_json"] = client_config_json
templates.env.globals["i18n_client_config_json"] = i18n_client_config_json
templates.env.globals["locale_choices"] = LOCALE_CHOICES
templates.env.globals["account_initials"] = accounts.account_initials
templates.env.globals["account_initials_hue"] = accounts.account_initials_hue


def _highlight_code_filter(code: str, language: str = "") -> Markup:
    return Markup(render_code_block(code, normalize_language(language)))


templates.env.filters["highlight_code"] = _highlight_code_filter


@pass_context
def _translate(context, key: str, **kwargs):
    locale = context.get("locale")
    if not locale:
        request = context.get("request")
        locale = getattr(getattr(request, "state", None), "locale", None)
    return t(normalize_locale(locale), key, **kwargs)


templates.env.globals["_"] = _translate


def render_template(request: Request, name: str, context: dict | None = None, **kwargs):
    locale = normalize_locale(getattr(request.state, "locale", None))
    ctx = {k: v for k, v in (context or {}).items() if k != "request"}
    ctx["locale"] = locale
    return templates.TemplateResponse(request, name, ctx, **kwargs)
