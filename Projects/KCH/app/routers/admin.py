from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import generate_password, hash_password, require_admin
from database import get_db
from importer import CSV_DIR, import_from_upload, run_import
from models import Evidence, TesterType, TestResult, TestRun, TestScript, User
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


@router.post("/runs/{run_id}/delete")
async def delete_run(
    run_id: str,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    run = db.get(TestRun, run_id)
    if run:
        results = db.query(TestResult).filter(TestResult.run_id == run_id).all()
        for result in results:
            for ev in db.query(Evidence).filter(Evidence.result_id == result.result_id).all():
                if ev.file_path:
                    try:
                        Path(ev.file_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                db.delete(ev)
            db.delete(result)
        db.delete(run)
        db.commit()
    return RedirectResponse("/reports", status_code=303)

# ── User management ───────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    tester_types = db.query(TesterType).order_by(TesterType.sort_order).all()
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "users": users, "tester_types": tester_types},
    )


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def admin_user_detail(
    user_id: str,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        return RedirectResponse("/admin/users", status_code=303)

    from models import TestResult, TestScript
    runs = (
        db.query(TestRun)
        .filter(TestRun.tester_email == user.email)
        .order_by(TestRun.started_at.desc())
        .all()
    )

    # Build per-run summary counts
    run_summaries = []
    for run in runs:
        results = db.query(TestResult).filter(TestResult.run_id == run.run_id).all()
        total = len(results)
        passed = sum(1 for r in results if r.outcome == "Pass")
        failed = sum(1 for r in results if r.outcome == "Fail")
        blocked = sum(1 for r in results if r.outcome == "Blocked")
        not_tested = sum(1 for r in results if r.outcome is None or r.outcome == "Not Tested")
        run_summaries.append({
            "run": run,
            "total": total,
            "passed": passed,
            "failed": failed,
            "blocked": blocked,
            "not_tested": not_tested,
            "pct": round(passed / total * 100) if total else 0,
        })

    tester_types = db.query(TesterType).order_by(TesterType.sort_order).all()
    return templates.TemplateResponse(
        "admin/user_detail.html",
        {
            "request": request,
            "user": user,
            "run_summaries": run_summaries,
            "tester_types": tester_types,
        },
    )


@router.get("/users/{user_id}/run/{run_id}/results", response_class=HTMLResponse)
async def admin_user_run_results(
    user_id: str,
    run_id: str,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from models import TestResult, TestScript
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
    return templates.TemplateResponse(
        "admin/partials/run_results.html",
        {"request": request, "results": results, "scripts": scripts},
    )


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: str,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user:
        new_pw = generate_password()
        user.password_hash = hash_password(new_pw)
        db.commit()
        users = db.query(User).order_by(User.created_at.desc()).all()
        tester_types = db.query(TesterType).order_by(TesterType.sort_order).all()
        return templates.TemplateResponse(
            "admin/users.html",
            {
                "request": request,
                "users": users,
                "tester_types": tester_types,
                "reset_info": {"name": user.name, "email": user.email, "password": new_pw},
            },
        )
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/assign-types")
async def admin_assign_types(
    user_id: str,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    selected = form.getlist("tester_types")
    user = db.get(User, user_id)
    if user:
        import json as _json
        user.tester_types = _json.dumps(selected)
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/toggle")
async def admin_toggle_user(
    user_id: str,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user:
        user.is_active = not user.is_active
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)
