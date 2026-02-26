from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from importer import CSV_DIR, import_from_upload, run_import
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
            "upload_log": None,
            "upload_error": None,
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
            "upload_log": None,
            "upload_error": None,
        },
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload_csv(
    request: Request,
    tester_type: str = Form(...),
    file: UploadFile = File(...),
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    upload_log = None
    upload_error = None

    if not file.filename.endswith(".csv"):
        upload_error = "Only CSV files are accepted."
    else:
        raw = await file.read()
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw.decode("latin-1")
        upload_log = import_from_upload(db, tester_type, content)

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
            "import_log": None,
            "upload_log": upload_log,
            "upload_error": upload_error,
        },
    )
