import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from auth import (
    get_session,
    hash_password,
    require_user_session,
    sign_session,
    verify_password,
)
from database import get_db
from models import TestRun, User
from shared import templates

router = APIRouter(prefix="/user")


@router.get("/login", response_class=HTMLResponse)
async def user_login_page(
    request: Request,
    existing: str = "",
):
    return templates.TemplateResponse(
        "user/login.html",
        {"request": request, "existing": existing == "1", "error": None},
    )


@router.post("/login")
async def user_login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not user.is_active or not verify_password(user.password_hash, password):
        return templates.TemplateResponse(
            "user/login.html",
            {"request": request, "existing": False, "error": "Invalid email or password."},
            status_code=401,
        )

    user.last_login = datetime.utcnow()
    db.commit()

    session_data = {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "is_admin": bool(user.is_admin),
    }
    token = sign_session(session_data)
    response = RedirectResponse("/user/dashboard", status_code=303)
    response.set_cookie("session", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return response


@router.get("/logout")
async def user_logout():
    response = RedirectResponse("/user/login", status_code=303)
    response.delete_cookie("session")
    return response


@router.get("/credentials", response_class=HTMLResponse)
async def user_credentials(
    request: Request,
    session: dict = Depends(require_user_session),
):
    temp = session.get("temp_creds")
    if not temp:
        return RedirectResponse("/user/dashboard", status_code=303)
    return templates.TemplateResponse(
        "user/credentials.html",
        {
            "request": request,
            "email": temp.get("email"),
            "password": temp.get("password"),
            "run_id": temp.get("run_id"),
        },
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard(
    request: Request,
    session: dict = Depends(require_user_session),
    db: Session = Depends(get_db),
):
    user = db.get(User, session["user_id"])
    if not user:
        response = RedirectResponse("/user/login", status_code=303)
        response.delete_cookie("session")
        return response

    runs = (
        db.query(TestRun)
        .filter(TestRun.tester_email == user.email)
        .order_by(TestRun.started_at.desc())
        .all()
    )
    pw_error = request.query_params.get("pw_error")
    return templates.TemplateResponse(
        "user/dashboard.html",
        {
            "request": request,
            "user": user,
            "runs": runs,
            "show_password_modal": bool(user.force_password_change),
            "pw_error": pw_error,
        },
    )


@router.post("/change-password")
async def user_change_password(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    session: dict = Depends(require_user_session),
    db: Session = Depends(get_db),
):
    if new_password != confirm_password:
        return RedirectResponse("/user/dashboard?pw_error=Passwords+do+not+match.", status_code=303)
    if len(new_password) < 8:
        return RedirectResponse("/user/dashboard?pw_error=Password+must+be+at+least+8+characters.", status_code=303)

    user = db.get(User, session["user_id"])
    if user:
        user.password_hash = hash_password(new_password)
        user.force_password_change = False
        db.commit()

    return RedirectResponse("/user/dashboard", status_code=303)
