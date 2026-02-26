from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from importer import CSV_DIR, run_import
from models import TestRun, TestScript
from shared import templates

router = APIRouter(prefix="/admin")


@router.get("", response_class=HTMLResponse)
async def admin_index(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    script_counts = {
        "everyday": db.query(TestScript).filter(
            TestScript.tester_type == "everyday", TestScript.is_active == True
        ).count(),
        "power": db.query(TestScript).filter(
            TestScript.tester_type == "power", TestScript.is_active == True
        ).count(),
        "specialist": db.query(TestScript).filter(
            TestScript.tester_type == "specialist", TestScript.is_active == True
        ).count(),
        "total": db.query(TestScript).filter(TestScript.is_active == True).count(),
    }

    run_stats = {
        "total": db.query(TestRun).count(),
        "submitted": db.query(TestRun).filter(TestRun.status == "SUBMITTED").count(),
        "in_progress": db.query(TestRun).filter(TestRun.status == "IN_PROGRESS").count(),
    }

    latest_script = (
        db.query(TestScript).order_by(TestScript.updated_at.desc()).first()
    )
    last_import = latest_script.updated_at if latest_script else None

    return templates.TemplateResponse(
        "admin/index.html",
        {
            "request": request,
            "script_counts": script_counts,
            "run_stats": run_stats,
            "last_import": last_import,
            "import_log": None,
        },
    )


@router.post("/import", response_class=HTMLResponse)
async def trigger_import(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    counts = run_import(db, CSV_DIR)

    script_counts = {
        "everyday": db.query(TestScript).filter(
            TestScript.tester_type == "everyday", TestScript.is_active == True
        ).count(),
        "power": db.query(TestScript).filter(
            TestScript.tester_type == "power", TestScript.is_active == True
        ).count(),
        "specialist": db.query(TestScript).filter(
            TestScript.tester_type == "specialist", TestScript.is_active == True
        ).count(),
        "total": db.query(TestScript).filter(TestScript.is_active == True).count(),
    }

    run_stats = {
        "total": db.query(TestRun).count(),
        "submitted": db.query(TestRun).filter(TestRun.status == "SUBMITTED").count(),
        "in_progress": db.query(TestRun).filter(TestRun.status == "IN_PROGRESS").count(),
    }

    latest_script = db.query(TestScript).order_by(TestScript.updated_at.desc()).first()
    last_import = latest_script.updated_at if latest_script else None

    return templates.TemplateResponse(
        "admin/index.html",
        {
            "request": request,
            "script_counts": script_counts,
            "run_stats": run_stats,
            "last_import": last_import,
            "import_log": counts,
        },
    )
