import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from auth import get_session, require_session
from database import get_db
from models import TestResult, TestRun, TestScript
from schemas import StartRunRequest
from shared import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: dict = Depends(require_session)):
    return RedirectResponse("/start", status_code=302)


@router.get("/start", response_class=HTMLResponse)
async def start_page(request: Request, session: dict = Depends(require_session)):
    return templates.TemplateResponse("start.html", {"request": request, "errors": {}, "form": {}})


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
    session: dict = Depends(require_session),
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

    try:
        validated = StartRunRequest(**form_data)
    except ValidationError as e:
        errors = {err["loc"][-1]: err["msg"] for err in e.errors()}
        return templates.TemplateResponse(
            "start.html",
            {"request": request, "errors": errors, "form": form_data},
            status_code=422,
        )

    run_id = str(uuid.uuid4())
    run = TestRun(
        run_id=run_id,
        tester_name=validated.tester_name,
        tester_email=validated.tester_email,
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

    # Seed blank results for all active scripts of this type
    scripts = (
        db.query(TestScript)
        .filter(TestScript.tester_type == validated.tester_type, TestScript.is_active == True)
        .order_by(TestScript.script_id)
        .all()
    )
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
    return RedirectResponse(f"/run/{run_id}", status_code=302)


@router.get("/run/{run_id}", response_class=HTMLResponse)
async def run_page(
    run_id: str,
    request: Request,
    session: dict = Depends(require_session),
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
    session: dict = Depends(require_session),
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
    session: dict = Depends(require_session),
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
