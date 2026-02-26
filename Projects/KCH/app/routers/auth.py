import os
from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import ACCESS_CODE, ADMIN_CODE, get_session, sign_session
from shared import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    session = get_session(request)
    if session:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    response: Response,
    access_code: str = Form(...),
):
    is_admin = access_code == ADMIN_CODE
    if access_code == ACCESS_CODE or is_admin:
        token = sign_session({"authenticated": True, "is_admin": is_admin})
        redirect = RedirectResponse("/", status_code=302)
        redirect.set_cookie(
            "session",
            token,
            httponly=True,
            samesite="lax",
            max_age=86400 * 7,
        )
        return redirect
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid access code. Please try again."},
        status_code=401,
    )


@router.get("/logout")
async def logout():
    redirect = RedirectResponse("/login", status_code=302)
    redirect.delete_cookie("session")
    return redirect
