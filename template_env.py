from fastapi.templating import Jinja2Templates

import config
from static_assets import static_url


def create_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory="templates")
    templates.env.globals["wiki_edit_enabled"] = config.WIKI_EDIT_ENABLED
    templates.env.globals["static_url"] = static_url
    return templates
