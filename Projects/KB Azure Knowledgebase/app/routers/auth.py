from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from auth import (
    clear_login_attempts,
    get_session,
    is_rate_limited,
    record_failed_login,
    sign_session,
    verify_password,
)
from database import get_db
from models import User
from shared import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_session(request):
        return RedirectResponse("/app", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"

    if is_rate_limited(ip):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Too many failed attempts. Please wait 5 minutes."},
            status_code=429,
        )

    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.password_hash):
        record_failed_login(ip)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password."},
            status_code=401,
        )

    if not user.is_active:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Your account is disabled. Contact an administrator."},
            status_code=403,
        )

    clear_login_attempts(ip)

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    token = sign_session({
        "user_id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
    })
    redirect = RedirectResponse("/admin" if user.is_admin else "/app", status_code=302)
    redirect.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
    )
    return redirect


@router.get("/logout")
async def logout():
    redirect = RedirectResponse("/login", status_code=302)
    redirect.delete_cookie("session")
    return redirect
