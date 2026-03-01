from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from importer import CSV_DIR, import_from_upload, run_import
from models import TesterType, TestRun, TestScript
from shared import templates

router = APIRouter(prefix="/admin")


def _page_context(request: Request, db: Session, **extra) -> dict:
    all_types = db.query(TesterType).order_by(TesterType.sort_order).all()
    active_types = [tt for tt in all_types if tt.is_active]
    script_counts = [
        {
            "slug": tt.slug,
            "label": tt.label,
            "count": db.query(TestScript).filter(
                TestScript.tester_type == tt.slug, TestScript.is_active == True
            ).count(),
        }
        for tt in all_types
    ]
    total = db.query(TestScript).filter(TestScript.is_active == True).count()
    run_stats = {
        "total": db.query(TestRun).count(),
        "submitted": db.query(TestRun).filter(TestRun.status == "SUBMITTED").count(),
        "in_progress": db.query(TestRun).filter(TestRun.status == "IN_PROGRESS").count(),
    }
    latest = db.query(TestScript).order_by(TestScript.updated_at.desc()).first()
    return {
        "request": request,
        "all_tester_types": all_types,
        "tester_types": active_types,
        "script_counts": script_counts,
        "script_total": total,
        "run_stats": run_stats,
        "last_import": latest.updated_at if latest else None,
        "import_log": None,
        "upload_log": None,
        "upload_error": None,
        "type_error": None,
        **extra,
    }


@router.get("", response_class=HTMLResponse)
async def admin_index(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse("admin/index.html", _page_context(request, db))


@router.post("/import", response_class=HTMLResponse)
async def trigger_import(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    counts = run_import(db, CSV_DIR)
    return templates.TemplateResponse(
        "admin/index.html", _page_context(request, db, import_log=counts)
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

    return templates.TemplateResponse(
        "admin/index.html",
        _page_context(request, db, upload_log=upload_log, upload_error=upload_error),
    )


@router.post("/tester-types", response_class=HTMLResponse)
async def add_tester_type(
    request: Request,
    slug: str = Form(...),
    label: str = Form(...),
    description: str = Form(""),
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    slug = slug.strip().lower().replace(" ", "_")
    type_error = None
    if not slug or not label.strip():
        type_error = "Slug and label are required."
    elif db.get(TesterType, slug):
        type_error = f"Tester type '{slug}' already exists."
    else:
        max_order = db.query(func.max(TesterType.sort_order)).scalar() or 0
        db.add(TesterType(
            slug=slug,
            label=label.strip(),
            description=description.strip(),
            sort_order=max_order + 1,
            is_active=True,
        ))
        db.commit()
    return templates.TemplateResponse(
        "admin/index.html", _page_context(request, db, type_error=type_error)
    )


@router.post("/tester-types/{slug}/toggle", response_class=HTMLResponse)
async def toggle_tester_type(
    slug: str,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tt = db.get(TesterType, slug)
    if tt:
        tt.is_active = not tt.is_active
        db.commit()
    return templates.TemplateResponse("admin/index.html", _page_context(request, db))
