import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_session
from database import get_db
from models import TestResult, TestRun, TestScript

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def reports_index(
    request: Request,
    tester_type: str = None,
    environment: str = None,
    status: str = None,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    query = db.query(TestRun)
    if tester_type:
        query = query.filter(TestRun.tester_type == tester_type)
    if environment:
        query = query.filter(TestRun.environment == environment)
    if status:
        query = query.filter(TestRun.status == status)

    runs = query.order_by(TestRun.started_at.desc()).all()

    # Annotate each run with counts
    run_data = []
    for run in runs:
        results = db.query(TestResult).filter(TestResult.run_id == run.run_id).all()
        run_data.append({
            "run": run,
            "total": len(results),
            "pass": sum(1 for r in results if r.outcome == "Pass"),
            "fail": sum(1 for r in results if r.outcome == "Fail"),
            "blocked": sum(1 for r in results if r.outcome == "Blocked"),
            "not_tested": sum(1 for r in results if r.outcome is None or r.outcome == "Not Tested"),
        })

    return templates.TemplateResponse(
        "reports/index.html",
        {
            "request": request,
            "run_data": run_data,
            "filters": {"tester_type": tester_type, "environment": environment, "status": status},
        },
    )


@router.get("/run/{run_id}", response_class=HTMLResponse)
async def run_detail(
    run_id: str,
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    run = db.get(TestRun, run_id)
    if not run:
        return HTMLResponse("Run not found", status_code=404)

    results = (
        db.query(TestResult)
        .filter(TestResult.run_id == run_id)
        .order_by(TestResult.script_id)
        .all()
    )
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

    return templates.TemplateResponse(
        "reports/run_detail.html",
        {
            "request": request,
            "run": run,
            "results": results,
            "scripts": scripts,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "blocked_count": blocked_count,
            "not_tested_count": not_tested_count,
            "total": len(results),
        },
    )


@router.get("/scripts", response_class=HTMLResponse)
async def scripts_summary(
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    scripts = db.query(TestScript).filter(TestScript.is_active == True).order_by(TestScript.script_id).all()
    script_stats = []
    for script in scripts:
        results = db.query(TestResult).filter(TestResult.script_id == script.script_id).all()
        total = len(results)
        passes = sum(1 for r in results if r.outcome == "Pass")
        fails = sum(1 for r in results if r.outcome == "Fail")
        pass_rate = round(passes / total * 100) if total > 0 else None
        script_stats.append({
            "script": script,
            "total_runs": total,
            "pass_count": passes,
            "fail_count": fails,
            "pass_rate": pass_rate,
        })

    return templates.TemplateResponse(
        "reports/scripts.html",
        {"request": request, "script_stats": script_stats},
    )


@router.get("/failures", response_class=HTMLResponse)
async def failures_report(
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    failures = (
        db.query(TestResult)
        .filter(TestResult.outcome.in_(["Fail", "Blocked"]))
        .order_by(TestResult.failure_category, TestResult.script_id)
        .all()
    )
    scripts = {
        s.script_id: s
        for s in db.query(TestScript)
        .filter(TestScript.script_id.in_([r.script_id for r in failures]))
        .all()
    }
    runs = {
        r.run_id: r
        for r in db.query(TestRun)
        .filter(TestRun.run_id.in_([f.run_id for f in failures]))
        .all()
    }

    # Group by failure_category
    grouped: dict[str, list] = {}
    for f in failures:
        cat = f.failure_category or "Uncategorised"
        grouped.setdefault(cat, []).append(f)

    return templates.TemplateResponse(
        "reports/failures.html",
        {
            "request": request,
            "grouped": grouped,
            "scripts": scripts,
            "runs": runs,
            "total": len(failures),
        },
    )


@router.get("/retest", response_class=HTMLResponse)
async def retest_report(
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    retests = (
        db.query(TestResult)
        .filter(TestResult.retest_needed == True)
        .order_by(TestResult.script_id)
        .all()
    )
    scripts = {
        s.script_id: s
        for s in db.query(TestScript)
        .filter(TestScript.script_id.in_([r.script_id for r in retests]))
        .all()
    }
    runs = {
        r.run_id: r
        for r in db.query(TestRun)
        .filter(TestRun.run_id.in_([f.run_id for f in retests]))
        .all()
    }

    return templates.TemplateResponse(
        "reports/retest.html",
        {
            "request": request,
            "retests": retests,
            "scripts": scripts,
            "runs": runs,
            "total": len(retests),
        },
    )


@router.get("/export")
async def export_csv(
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    runs = db.query(TestRun).order_by(TestRun.started_at.desc()).all()
    results_all = db.query(TestResult).all()
    scripts_all = {s.script_id: s for s in db.query(TestScript).all()}
    results_by_run: dict[str, list] = {}
    for r in results_all:
        results_by_run.setdefault(r.run_id, []).append(r)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "run_id", "tester_name", "tester_email", "tester_type", "department",
        "environment", "device", "browser", "run_status", "started_at", "submitted_at",
        "script_id", "title", "category", "tester_type_script",
        "outcome", "failure_category", "happened", "expected_instead",
        "retest_needed", "comments",
    ])

    for run in runs:
        for result in results_by_run.get(run.run_id, []):
            script = scripts_all.get(result.script_id)
            writer.writerow([
                run.run_id,
                run.tester_name,
                run.tester_email,
                run.tester_type,
                run.department or "",
                run.environment,
                run.device or "",
                run.browser or "",
                run.status,
                run.started_at.isoformat() if run.started_at else "",
                run.submitted_at.isoformat() if run.submitted_at else "",
                result.script_id,
                script.title if script else "",
                script.category if script else "",
                script.tester_type if script else "",
                result.outcome or "",
                result.failure_category or "",
                result.happened or "",
                result.expected_instead or "",
                "Yes" if result.retest_needed else "No",
                result.comments or "",
            ])

    output.seek(0)
    filename = f"uat_results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
