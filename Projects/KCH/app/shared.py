from fastapi.templating import Jinja2Templates

from auth import get_session

templates = Jinja2Templates(directory="templates")


def _is_admin(request) -> bool:
    session = get_session(request)
    return bool(session and session.get("is_admin"))


templates.env.globals["is_admin"] = _is_admin

import json as _json

def _from_json(value):
    try:
        return _json.loads(value) if value else []
    except Exception:
        return []

templates.env.filters["from_json"] = _from_json
