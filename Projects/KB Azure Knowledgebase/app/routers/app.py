from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from auth import get_session, require_session
from database import get_db
from models import (
    AuditLog, Department, DocumentType, ItemFile,
    KnowledgeItem, Source, Status, StatusHistory, User
)
from shared import templates
import storage

router = APIRouter(prefix="/app")


def _get_user(session: dict, db: Session) -> User:
    return db.query(User).filter(User.id == session["user_id"]).first()


@router.get("", response_class=HTMLResponse)
async def app_index(request: Request, session: dict = Depends(require_session)):
    return RedirectResponse("/app/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    user_id = session["user_id"]
    user = _get_user(session, db)
    statuses = db.query(Status).filter(Status.is_active == True).order_by(Status.sort_order).all()

    counts = {}
    for s in statuses:
        counts[s.name] = db.query(KnowledgeItem).filter(
            KnowledgeItem.owner_id == user_id,
            KnowledgeItem.status_id == s.id,
        ).count()

    total = db.query(KnowledgeItem).filter(KnowledgeItem.owner_id == user_id).count()

    dept_total = None
    if user and user.department_id:
        dept_total = db.query(KnowledgeItem).filter(
            KnowledgeItem.department_id == user.department_id
        ).count()

    recent = (
        db.query(KnowledgeItem)
        .filter(KnowledgeItem.owner_id == user_id)
        .order_by(KnowledgeItem.updated_at.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse("app/dashboard.html", {
        "request": request,
        "status_counts": counts,
        "total": total,
        "dept_total": dept_total,
        "department": user.department if user else None,
        "recent_items": recent,
        "statuses": statuses,
    })


@router.get("/items", response_class=HTMLResponse)
async def items_list(
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
    source_id: int = None,
    department_id: int = None,
    document_type_id: int = None,
    status_id: int = None,
    q: str = None,
):
    user_id = session["user_id"]
    query = db.query(KnowledgeItem).filter(KnowledgeItem.owner_id == user_id)

    if source_id:
        query = query.filter(KnowledgeItem.source_id == source_id)
    if department_id:
        query = query.filter(KnowledgeItem.department_id == department_id)
    if document_type_id:
        query = query.filter(KnowledgeItem.document_type_id == document_type_id)
    if status_id:
        query = query.filter(KnowledgeItem.status_id == status_id)
    if q:
        query = query.filter(KnowledgeItem.title.ilike(f"%{q}%"))

    items = query.order_by(KnowledgeItem.updated_at.desc()).all()

    return templates.TemplateResponse("app/items.html", {
        "request": request,
        "items": items,
        "sources": db.query(Source).filter(Source.is_active == True).order_by(Source.name).all(),
        "departments": db.query(Department).order_by(Department.name).all(),
        "document_types": db.query(DocumentType).order_by(DocumentType.name).all(),
        "statuses": db.query(Status).filter(Status.is_active == True).order_by(Status.sort_order).all(),
        "filters": {
            "source_id": source_id,
            "department_id": department_id,
            "document_type_id": document_type_id,
            "status_id": status_id,
            "q": q or "",
        },
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
    })


@router.get("/items/new", response_class=HTMLResponse)
async def new_item_form(
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    default_review = (datetime.utcnow() + timedelta(days=365)).strftime("%Y-%m-%d")
    return templates.TemplateResponse("app/item_new.html", {
        "request": request,
        "sources": db.query(Source).filter(Source.is_active == True).order_by(Source.name).all(),
        "departments": db.query(Department).order_by(Department.name).all(),
        "document_types": db.query(DocumentType).order_by(DocumentType.name).all(),
        "errors": {},
        "form": {"review_due_date": default_review},
        "default_review": default_review,
    })


@router.post("/items/new")
async def new_item_submit(
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
    title: str = Form(...),
    summary: str = Form(""),
    text_content: str = Form(""),
    source_id: int = Form(None),
    department_id: int = Form(None),
    document_type_id: int = Form(None),
    review_due_date: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    errors = {}
    if not title.strip():
        errors["title"] = "Title is required."

    parsed_review = None
    if review_due_date:
        try:
            parsed_review = datetime.strptime(review_due_date, "%Y-%m-%d")
        except ValueError:
            errors["review_due_date"] = "Invalid date format."

    default_review = (datetime.utcnow() + timedelta(days=365)).strftime("%Y-%m-%d")

    if errors:
        return templates.TemplateResponse("app/item_new.html", {
            "request": request,
            "sources": db.query(Source).filter(Source.is_active == True).order_by(Source.name).all(),
            "departments": db.query(Department).order_by(Department.name).all(),
            "document_types": db.query(DocumentType).order_by(DocumentType.name).all(),
            "errors": errors,
            "form": {"title": title, "summary": summary, "text_content": text_content,
                     "source_id": source_id, "department_id": department_id,
                     "document_type_id": document_type_id,
                     "review_due_date": review_due_date or default_review},
            "default_review": default_review,
        }, status_code=422)

    if not parsed_review:
        parsed_review = datetime.utcnow() + timedelta(days=365)

    # Find submitted status
    submitted_status = db.query(Status).filter(Status.name == "Submitted").first()

    item = KnowledgeItem(
        title=title.strip(),
        summary=summary.strip() or None,
        text_content=text_content.strip() or None,
        source_id=source_id or None,
        department_id=department_id or None,
        document_type_id=document_type_id or None,
        owner_id=session["user_id"],
        status_id=submitted_status.id if submitted_status else None,
        review_due_date=parsed_review,
    )
    db.add(item)
    db.flush()

    # Record initial status history
    if submitted_status:
        db.add(StatusHistory(
            item_id=item.id,
            from_status_id=None,
            to_status_id=submitted_status.id,
            changed_by_id=session["user_id"],
            note="Item submitted",
        ))

    # Handle file uploads
    for upload in files:
        if not upload.filename:
            continue
        data = await upload.read()
        if len(data) > storage.UPLOAD_MAX_BYTES:
            continue  # silently skip oversized files
        r2_key = storage.upload_file(item.id, upload.filename, data, upload.content_type or "application/octet-stream")

        db.add(ItemFile(
            item_id=item.id,
            original_filename=upload.filename,
            r2_key=r2_key,
            mime_type=upload.content_type,
            file_size=len(data),
        ))

    AuditLog.log(db, session["user_id"], "item.created", "knowledge_item", item.id,
                 title=title)
    db.commit()

    return RedirectResponse(f"/app/items/{item.id}?msg=Item submitted successfully", status_code=303)


@router.get("/items/{item_id}", response_class=HTMLResponse)
async def item_detail(
    item_id: int,
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    item = db.query(KnowledgeItem).filter(
        KnowledgeItem.id == item_id,
        KnowledgeItem.owner_id == session["user_id"],
    ).first()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    file_urls = {f.id: storage.presign_url(f.r2_key) for f in item.files}

    statuses = db.query(Status).filter(
        Status.is_active == True,
        Status.admin_only == False,
    ).order_by(Status.sort_order).all()

    can_edit = not item.is_locked and item.status and item.status.name in (
        "Submitted", "Under Review", "In Progress"
    )

    from shared import review_ring
    return templates.TemplateResponse("app/item_detail.html", {
        "request": request,
        "item": item,
        "file_urls": file_urls,
        "statuses": statuses,
        "can_edit": can_edit,
        "ring": review_ring(item),
        "sources": db.query(Source).filter(Source.is_active == True).order_by(Source.name).all(),
        "departments": db.query(Department).order_by(Department.name).all(),
        "document_types": db.query(DocumentType).order_by(DocumentType.name).all(),
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
    })


@router.post("/items/{item_id}")
async def item_update(
    item_id: int,
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
    title: str = Form(...),
    summary: str = Form(""),
    text_content: str = Form(""),
    source_id: int = Form(None),
    department_id: int = Form(None),
    document_type_id: int = Form(None),
    review_due_date: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    item = db.query(KnowledgeItem).filter(
        KnowledgeItem.id == item_id,
        KnowledgeItem.owner_id == session["user_id"],
    ).first()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    if item.is_locked or (item.status and item.status.name not in ("Submitted", "Under Review", "In Progress")):
        return RedirectResponse(f"/app/items/{item_id}?error=Item cannot be edited in its current state", status_code=303)

    if not title.strip():
        return RedirectResponse(f"/app/items/{item_id}?error=Title is required", status_code=303)

    item.title = title.strip()
    item.summary = summary.strip() or None
    item.text_content = text_content.strip() or None
    item.source_id = source_id or None
    item.department_id = department_id or None
    item.document_type_id = document_type_id or None
    item.updated_at = datetime.utcnow()
    if review_due_date:
        try:
            item.review_due_date = datetime.strptime(review_due_date, "%Y-%m-%d")
        except ValueError:
            pass

    for upload in files:
        if not upload.filename:
            continue
        data = await upload.read()
        if len(data) > storage.UPLOAD_MAX_BYTES:
            continue
        r2_key = storage.upload_file(item.id, upload.filename, data, upload.content_type or "application/octet-stream")

        db.add(ItemFile(
            item_id=item.id,
            original_filename=upload.filename,
            r2_key=r2_key,
            mime_type=upload.content_type,
            file_size=len(data),
        ))

    AuditLog.log(db, session["user_id"], "item.updated", "knowledge_item", item_id)
    db.commit()

    return RedirectResponse(f"/app/items/{item_id}?msg=Item updated", status_code=303)


@router.get("/department", response_class=HTMLResponse)
async def department_items(
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
    status_id: int = None,
    document_type_id: int = None,
    source_id: int = None,
    q: str = None,
):
    user = _get_user(session, db)

    if not user or not user.department_id:
        return templates.TemplateResponse("app/department.html", {
            "request": request,
            "no_department": True,
            "items": [],
            "department": None,
            "statuses": [],
            "document_types": [],
            "sources": [],
            "filters": {},
        })

    query = db.query(KnowledgeItem).filter(
        KnowledgeItem.department_id == user.department_id
    )

    if status_id:
        query = query.filter(KnowledgeItem.status_id == status_id)
    if document_type_id:
        query = query.filter(KnowledgeItem.document_type_id == document_type_id)
    if source_id:
        query = query.filter(KnowledgeItem.source_id == source_id)
    if q:
        query = query.filter(KnowledgeItem.title.ilike(f"%{q}%"))

    items = query.order_by(KnowledgeItem.updated_at.desc()).all()

    return templates.TemplateResponse("app/department.html", {
        "request": request,
        "no_department": False,
        "items": items,
        "department": user.department,
        "statuses": db.query(Status).filter(Status.is_active == True).order_by(Status.sort_order).all(),
        "document_types": db.query(DocumentType).order_by(DocumentType.name).all(),
        "sources": db.query(Source).filter(Source.is_active == True).order_by(Source.name).all(),
        "filters": {
            "status_id": status_id,
            "document_type_id": document_type_id,
            "source_id": source_id,
            "q": q or "",
        },
    })


@router.get("/department/items/{item_id}", response_class=HTMLResponse)
async def department_item_detail(
    item_id: int,
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    user = _get_user(session, db)

    if not user or not user.department_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403)

    # Item must be in the same department — not restricted by owner
    item = db.query(KnowledgeItem).filter(
        KnowledgeItem.id == item_id,
        KnowledgeItem.department_id == user.department_id,
    ).first()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    file_urls = {f.id: storage.presign_url(f.r2_key) for f in item.files}

    return templates.TemplateResponse("app/item_detail.html", {
        "request": request,
        "item": item,
        "file_urls": file_urls,
        "statuses": [],
        "can_edit": False,
        "sources": [],
        "departments": [],
        "document_types": [],
        "is_department_view": True,
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
    })


@router.post("/items/{item_id}/files/{file_id}/delete")
async def delete_file(
    item_id: int,
    file_id: int,
    request: Request,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    item = db.query(KnowledgeItem).filter(
        KnowledgeItem.id == item_id,
        KnowledgeItem.owner_id == session["user_id"],
    ).first()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    f = db.query(ItemFile).filter(ItemFile.id == file_id, ItemFile.item_id == item_id).first()
    if f:
        storage.delete_file(f.r2_key)
        db.delete(f)
        db.commit()

    return RedirectResponse(f"/app/items/{item_id}?msg=File deleted", status_code=303)
