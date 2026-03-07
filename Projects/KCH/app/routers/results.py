import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from auth import require_any_session, require_session
from database import get_db
from models import Evidence, TestResult, TestRun, TestScript
from schemas import SaveResultRequest
from shared import templates

router = APIRouter()

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/gif",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv", "text/plain",
    "application/zip",
}


def _get_result(db: Session, run_id: str, script_id: str) -> TestResult | None:
    return (
        db.query(TestResult)
        .filter(TestResult.run_id == run_id, TestResult.script_id == script_id)
        .first()
    )


def _build_card_context(db: Session, run_id: str, script_id: str, error: str | None = None):
    run = db.get(TestRun, run_id)
    script = db.get(TestScript, script_id)
    result = _get_result(db, run_id, script_id)
    evidence = (
        db.query(Evidence).filter(Evidence.result_id == result.result_id).all()
        if result else []
    )
    all_results = (
        db.query(TestResult).filter(TestResult.run_id == run_id).order_by(TestResult.script_id).all()
    )
    # Find next not-tested script
    result_list = all_results
    current_idx = next((i for i, r in enumerate(result_list) if r.script_id == script_id), 0)
    next_script_id = None
    for r in result_list[current_idx + 1:]:
        if r.outcome is None:
            next_script_id = r.script_id
            break

    return {
        "run": run,
        "script": script,
        "result": result,
        "evidence": evidence,
        "next_script_id": next_script_id,
        "error": error,
        "pass_count": sum(1 for r in all_results if r.outcome == "Pass"),
        "fail_count": sum(1 for r in all_results if r.outcome == "Fail"),
        "blocked_count": sum(1 for r in all_results if r.outcome == "Blocked"),
        "not_tested_count": sum(1 for r in all_results if r.outcome is None or r.outcome == "Not Tested"),
        "total": len(all_results),
    }


@router.get("/run/{run_id}/script/{script_id}", response_class=HTMLResponse)
async def get_script_card(
    run_id: str,
    script_id: str,
    request: Request,
    session: dict = Depends(require_any_session),
    db: Session = Depends(get_db),
):
    ctx = _build_card_context(db, run_id, script_id)
    ctx["request"] = request
    return templates.TemplateResponse("partials/script_card.html", ctx)


@router.post("/run/{run_id}/script/{script_id}/result", response_class=HTMLResponse)
async def save_result(
    run_id: str,
    script_id: str,
    request: Request,
    outcome: str = Form(None),
    failure_category: str = Form(None),
    happened: str = Form(None),
    expected_instead: str = Form(None),
    retest_needed: str = Form("off"),
    comments: str = Form(None),
    action: str = Form(None),
    session: dict = Depends(require_any_session),
    db: Session = Depends(get_db),
):
    try:
        validated = SaveResultRequest(
            outcome=outcome or None,
            failure_category=failure_category or None,
            happened=happened or None,
            expected_instead=expected_instead or None,
            retest_needed=retest_needed == "on",
            comments=comments or None,
        )
    except ValidationError as e:
        error_msg = "; ".join(err["msg"] for err in e.errors())
        ctx = _build_card_context(db, run_id, script_id, error=error_msg)
        ctx["request"] = request
        return templates.TemplateResponse("partials/script_card.html", ctx, status_code=422)

    result = _get_result(db, run_id, script_id)
    if result:
        result.outcome = validated.outcome
        result.failure_category = validated.failure_category
        result.happened = validated.happened
        result.expected_instead = validated.expected_instead
        result.retest_needed = validated.retest_needed
        result.comments = validated.comments
        result.updated_at = datetime.utcnow()
        db.commit()

    # If Save & Next, return the next untested script's card directly
    if action == "save_next":
        current_ctx = _build_card_context(db, run_id, script_id)
        next_id = current_ctx.get("next_script_id")
        if next_id:
            ctx = _build_card_context(db, run_id, next_id)
            ctx["request"] = request
            ctx["saved_script_id"] = script_id
            ctx["saved_outcome"] = validated.outcome or ""
            return templates.TemplateResponse("partials/script_card.html", ctx)

    ctx = _build_card_context(db, run_id, script_id)
    ctx["request"] = request
    ctx["saved"] = True
    return templates.TemplateResponse("partials/script_card.html", ctx)


@router.post("/run/{run_id}/script/{script_id}/evidence", response_class=HTMLResponse)
async def upload_evidence(
    run_id: str,
    script_id: str,
    request: Request,
    evidence_url: str = Form(None),
    file: UploadFile = File(None),
    session: dict = Depends(require_any_session),
    db: Session = Depends(get_db),
):
    result = _get_result(db, run_id, script_id)
    if not result:
        return HTMLResponse("Result not found", status_code=404)

    if evidence_url:
        ev = Evidence(
            evidence_id=str(uuid.uuid4()),
            result_id=result.result_id,
            evidence_type="url",
            url=evidence_url,
            uploaded_at=datetime.utcnow(),
        )
        db.add(ev)
        db.commit()
    elif file and file.filename:
        if file.content_type not in ALLOWED_MIME:
            return HTMLResponse(f"File type '{file.content_type}' not allowed.", status_code=400)
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            return HTMLResponse("File exceeds 10 MB limit.", status_code=400)

        run_upload_dir = UPLOAD_DIR / run_id
        run_upload_dir.mkdir(parents=True, exist_ok=True)
        ev_id = str(uuid.uuid4())
        dest = run_upload_dir / f"{ev_id}_{file.filename}"
        dest.write_bytes(contents)

        ev = Evidence(
            evidence_id=ev_id,
            result_id=result.result_id,
            evidence_type="file",
            file_path=str(dest),
            file_name=file.filename,
            file_size=len(contents),
            mime_type=file.content_type,
            uploaded_at=datetime.utcnow(),
        )
        db.add(ev)
        db.commit()

    # Return updated evidence list partial
    evidence = db.query(Evidence).filter(Evidence.result_id == result.result_id).all()
    return templates.TemplateResponse(
        "partials/evidence_list.html",
        {"request": request, "evidence": evidence, "run_id": run_id, "result": result},
    )


@router.delete("/run/{run_id}/evidence/{evidence_id}", response_class=HTMLResponse)
async def delete_evidence(
    run_id: str,
    evidence_id: str,
    request: Request,
    session: dict = Depends(require_any_session),
    db: Session = Depends(get_db),
):
    ev = db.get(Evidence, evidence_id)
    if ev:
        if ev.file_path:
            try:
                Path(ev.file_path).unlink(missing_ok=True)
            except Exception:
                pass
        result_id = ev.result_id
        db.delete(ev)
        db.commit()
        evidence = db.query(Evidence).filter(Evidence.result_id == result_id).all()
        result = db.get(TestResult, result_id)
        return templates.TemplateResponse(
            "partials/evidence_list.html",
            {"request": request, "evidence": evidence, "run_id": run_id, "result": result},
        )
    return HTMLResponse("", status_code=200)
