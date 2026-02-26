from fastapi.templating import Jinja2Templates

from auth import get_session

templates = Jinja2Templates(directory="templates")


def _is_admin(request) -> bool:
    session = get_session(request)
    return bool(session and session.get("is_admin"))


templates.env.globals["is_admin"] = _is_admin
