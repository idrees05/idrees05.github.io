import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from auth import generate_password, hash_password, require_any_session, require_session, sign_session
from database import get_db
from models import TesterType, TestResult, TestRun, TestScript, User
from schemas import StartRunRequest
from shared import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: dict = Depends(require_any_session)):
    return RedirectResponse("/start", status_code=302)


@router.get("/start", response_class=HTMLResponse)
async def start_page(
    request: Request,
    db: Session = Depends(get_db),
):
    tester_types = (
        db.query(TesterType)
        .filter(TesterType.is_active == True)
        .order_by(TesterType.sort_order)
        .all()
    )
    return templates.TemplateResponse(
        "start.html", {"request": request, "errors": {}, "form": {}, "tester_types": tester_types}
    )


@router.post("/start")
async def start_submit(
    request: Request,
    tester_name: str = Form(...),
    tester_email: str = Form(...),
    tester_type: str = Form(...),
    department: str = Form(""),
    environment: str = Form(...),
    device: str = Form(""),
    browser: str = Form(""),
    access_issues: str = Form("off"),
    access_issues_notes: str = Form(""),
    db: Session = Depends(get_db),
):
    form_data = {
        "tester_name": tester_name,
        "tester_email": tester_email,
        "tester_type": tester_type,
        "department": department,
        "environment": environment,
        "device": device,
        "browser": browser,
        "access_issues": access_issues == "on",
        "access_issues_notes": access_issues_notes,
    }

    tester_types = (
        db.query(TesterType)
        .filter(TesterType.is_active == True)
        .order_by(TesterType.sort_order)
        .all()
    )

    try:
        validated = StartRunRequest(**form_data)
    except ValidationError as e:
        errors = {err["loc"][-1]: err["msg"] for err in e.errors()}
        return templates.TemplateResponse(
            "start.html",
            {"request": request, "errors": errors, "form": form_data, "tester_types": tester_types},
            status_code=422,
        )

    tt = db.get(TesterType, validated.tester_type)
    if not tt or not tt.is_active:
        return templates.TemplateResponse(
            "start.html",
            {
                "request": request,
                "errors": {"tester_type": "Invalid tester type selected."},
                "form": form_data,
                "tester_types": tester_types,
            },
            status_code=422,
        )

    # Fetch scripts before creating the run — reject early if none are available
    scripts = (
        db.query(TestScript)
        .filter(TestScript.tester_type == validated.tester_type, TestScript.is_active == True)
        .order_by(TestScript.script_id)
        .all()
    )
    if not scripts:
        return templates.TemplateResponse(
            "start.html",
            {
                "request": request,
                "errors": {"tester_type": "No active test scripts are available for this tester type. Please contact an administrator."},
                "form": form_data,
                "tester_types": tester_types,
            },
            status_code=422,
        )

    # Check for existing account
    email_lower = validated.tester_email.strip().lower()
    existing_user = db.query(User).filter(User.email == email_lower).first()
    if existing_user:
        return RedirectResponse("/user/login?existing=1", status_code=302)

    # Create new user account
    raw_password = generate_password()
    new_user = User(
        user_id=str(uuid.uuid4()),
        email=email_lower,
        name=validated.tester_name,
        department=validated.department,
        password_hash=hash_password(raw_password),
        tester_types=f'["{validated.tester_type}"]',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(new_user)

    run_id = str(uuid.uuid4())
    run = TestRun(
        run_id=run_id,
        tester_name=validated.tester_name,
        tester_email=email_lower,
        tester_type=validated.tester_type,
        department=validated.department,
        environment=validated.environment,
        device=validated.device,
        browser=validated.browser,
        access_issues=validated.access_issues,
        access_issues_notes=validated.access_issues_notes,
        status="IN_PROGRESS",
        started_at=datetime.utcnow(),
    )
    db.add(run)

    for script in scripts:
        result = TestResult(
            result_id=str(uuid.uuid4()),
            run_id=run_id,
            script_id=script.script_id,
            outcome=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(result)

    db.commit()

    # Set user session with temp credentials for display on /user/credentials
    session_data = {
        "user_id": new_user.user_id,
        "email": new_user.email,
        "name": new_user.name,
        "temp_creds": {
            "email": email_lower,
            "password": raw_password,
            "run_id": run_id,
        },
    }
    token = sign_session(session_data)
    response = RedirectResponse("/user/credentials", status_code=302)
    response.set_cookie("session", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return response


@router.get("/run/{run_id}", response_class=HTMLResponse)
async def run_page(
    run_id: str,
    request: Request,
    session: dict = Depends(require_any_session),
    db: Session = Depends(get_db),
):
    run = db.get(TestRun, run_id)
    if not run:
        return RedirectResponse("/start", status_code=302)

    results = (
        db.query(TestResult)
        .filter(TestResult.run_id == run_id)
        .order_by(TestResult.script_id)
        .all()
    )
    script_ids = [r.script_id for r in results]
    scripts = {
        s.script_id: s
        for s in db.query(TestScript).filter(TestScript.script_id.in_(script_ids)).all()
    }

    # Find first not-tested script for initial card load
    first_script = next(
        (scripts[r.script_id] for r in results if r.outcome is None and r.script_id in scripts),
        scripts[results[0].script_id] if results and results[0].script_id in scripts else None,
    )

    result_map = {r.script_id: r for r in results}

    # Build summary counts
    pass_count = sum(1 for r in results if r.outcome == "Pass")
    fail_count = sum(1 for r in results if r.outcome == "Fail")
    blocked_count = sum(1 for r in results if r.outcome == "Blocked")
    not_tested_count = sum(1 for r in results if r.outcome is None or r.outcome == "Not Tested")

    return templates.TemplateResponse(
        "run.html",
        {
            "request": request,
            "run": run,
            "results": results,
            "scripts": scripts,
            "result_map": result_map,
            "first_script": first_script,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "blocked_count": blocked_count,
            "not_tested_count": not_tested_count,
            "total": len(results),
        },
    )


@router.post("/run/{run_id}/submit")
async def submit_run(
    run_id: str,
    request: Request,
    session: dict = Depends(require_any_session),
    db: Session = Depends(get_db),
):
    run = db.get(TestRun, run_id)
    if not run or run.status == "SUBMITTED":
        return RedirectResponse(f"/run/{run_id}/complete", status_code=302)

    run.status = "SUBMITTED"
    run.submitted_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/run/{run_id}/complete", status_code=302)


@router.get("/run/{run_id}/complete", response_class=HTMLResponse)
async def run_complete(
    run_id: str,
    request: Request,
    session: dict = Depends(require_any_session),
    db: Session = Depends(get_db),
):
    run = db.get(TestRun, run_id)
    if not run:
        return RedirectResponse("/start", status_code=302)

    results = db.query(TestResult).filter(TestResult.run_id == run_id).all()
    scripts = {
        s.script_id: s
        for s in db.query(TestScript)
        .filter(TestScript.script_id.in_([r.script_id for r in results]))
        .all()
    }

    pass_count = sum(1 for r in results if r.outcome == "Pass")
    fail_count = sum(1 for r in results if r.outcome == "Fail")
    blocked_count = sum(1 for r in results if r.outcome == "Blocked")
    not_tested_count = sum(1 for r in results if r.outcome is None or r.outcome == "Not Tested")
    retest_count = sum(1 for r in results if r.retest_needed)

    failures = [r for r in results if r.outcome in ("Fail", "Blocked")]

    return templates.TemplateResponse(
        "complete.html",
        {
            "request": request,
            "run": run,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "blocked_count": blocked_count,
            "not_tested_count": not_tested_count,
            "retest_count": retest_count,
            "total": len(results),
            "failures": failures,
            "scripts": scripts,
        },
    )
