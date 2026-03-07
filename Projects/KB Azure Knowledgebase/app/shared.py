import math
import os
from datetime import datetime

from fastapi.templating import Jinja2Templates

from auth import get_session

_RING_R = 54
_RING_CIRCUMFERENCE = round(2 * math.pi * _RING_R, 2)  # ≈ 339.29


def review_label(review_due_date) -> str:
    """Human-readable countdown string, e.g. '9 months left', '3 days overdue'."""
    if not review_due_date:
        return ""
    diff = (review_due_date - datetime.utcnow()).days
    if diff < 0:
        n = abs(diff)
        return f"{n} day{'s' if n != 1 else ''} overdue"
    if diff == 0:
        return "Due today"
    if diff == 1:
        return "1 day left"
    if diff < 30:
        return f"{diff} days left"
    months = round(diff / 30.4)
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} left"
    years = diff // 365
    rem_months = round((diff % 365) / 30.4)
    if rem_months > 0:
        return f"{years}y {rem_months}m left"
    return f"{years} year{'s' if years != 1 else ''} left"


def review_ring(item) -> dict | None:
    """SVG ring data for the item detail timer. Returns None if no review date."""
    if not item.review_due_date or not item.created_at:
        return None
    now = datetime.utcnow()
    total_days = max(1, (item.review_due_date - item.created_at).days)
    days_remaining = (item.review_due_date - now).days
    progress = max(0.0, min(1.0, days_remaining / total_days))
    offset = round(_RING_CIRCUMFERENCE * (1 - progress), 2)

    if progress > 0.5:
        color = "var(--success)"
    elif progress > 0.25:
        color = "var(--warning)"
    else:
        color = "var(--danger)"

    return {
        "circumference": _RING_CIRCUMFERENCE,
        "offset": offset,
        "color": color,
        "days_remaining": days_remaining,
        "pct": round(progress * 100),
        "due_date": item.review_due_date.strftime("%d %b %Y"),
        "label": review_label(item.review_due_date),
        "overdue": days_remaining < 0,
    }

templates = Jinja2Templates(directory="templates")


def _is_admin(request) -> bool:
    session = get_session(request)
    return bool(session and session.get("is_admin"))


def _current_user_id(request):
    session = get_session(request)
    return session.get("user_id") if session else None


def _current_username(request) -> str:
    session = get_session(request)
    return session.get("username", "") if session else ""


templates.env.globals["is_admin"] = _is_admin
templates.env.globals["current_user_id"] = _current_user_id
templates.env.globals["current_username"] = _current_username
templates.env.globals["upload_max_mb"] = int(os.getenv("UPLOAD_MAX_MB", "20"))
templates.env.globals["review_label"] = review_label
templates.env.globals["review_ring"] = review_ring
