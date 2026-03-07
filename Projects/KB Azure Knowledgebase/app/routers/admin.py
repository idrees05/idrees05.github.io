import csv
import io
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import hash_password, require_admin
from database import get_db
from models import (
    AuditLog, Department, DocumentType, ItemFile,
    KnowledgeItem, Source, Status, StatusHistory, User
)
from shared import templates
import sharepoint
import storage

router = APIRouter(prefix="/admin")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    statuses = db.query(Status).filter(Status.is_active == True).order_by(Status.sort_order).all()

    by_status = {}
    for s in statuses:
        by_status[s.name] = db.query(KnowledgeItem).filter(KnowledgeItem.status_id == s.id).count()

    total = db.query(KnowledgeItem).count()
    total_users = db.query(User).filter(User.is_active == True, User.is_admin == False).count()

    recent = (
        db.query(KnowledgeItem)
        .order_by(KnowledgeItem.updated_at.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "by_status": by_status,
        "total": total,
        "total_users": total_users,
        "recent_items": recent,
        "statuses": statuses,
    })


# ── Items ─────────────────────────────────────────────────────────────────────

@router.get("/items", response_class=HTMLResponse)
async def admin_items(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    source_id: int = None,
    department_id: int = None,
    document_type_id: int = None,
    status_id: int = None,
    owner_id: int = None,
    q: str = None,
):
    query = db.query(KnowledgeItem)

    if source_id:
        query = query.filter(KnowledgeItem.source_id == source_id)
    if department_id:
        query = query.filter(KnowledgeItem.department_id == department_id)
    if document_type_id:
        query = query.filter(KnowledgeItem.document_type_id == document_type_id)
    if status_id:
        query = query.filter(KnowledgeItem.status_id == status_id)
    if owner_id:
        query = query.filter(KnowledgeItem.owner_id == owner_id)
    if q:
        query = query.filter(KnowledgeItem.title.ilike(f"%{q}%"))

    items = query.order_by(KnowledgeItem.updated_at.desc()).all()

    return templates.TemplateResponse("admin/items.html", {
        "request": request,
        "items": items,
        "sources": db.query(Source).order_by(Source.name).all(),
        "departments": db.query(Department).order_by(Department.name).all(),
        "document_types": db.query(DocumentType).order_by(DocumentType.name).all(),
        "statuses": db.query(Status).filter(Status.is_active == True).order_by(Status.sort_order).all(),
        "users": db.query(User).filter(User.is_admin == False, User.is_active == True).order_by(User.username).all(),
        "filters": {
            "source_id": source_id,
            "department_id": department_id,
            "document_type_id": document_type_id,
            "status_id": status_id,
            "owner_id": owner_id,
            "q": q or "",
        },
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
    })


@router.get("/items/export-csv")
async def export_items_csv(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    items = db.query(KnowledgeItem).order_by(KnowledgeItem.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "Source", "Department", "Document Type",
                     "Owner", "Status", "Created", "Updated"])
    for item in items:
        writer.writerow([
            item.id,
            item.title,
            item.source.name if item.source else "",
            item.department.name if item.department else "",
            item.document_type.name if item.document_type else "",
            item.owner.username if item.owner else "",
            item.status.name if item.status else "",
            item.created_at.strftime("%Y-%m-%d %H:%M") if item.created_at else "",
            item.updated_at.strftime("%Y-%m-%d %H:%M") if item.updated_at else "",
        ])

    AuditLog.log(db, session["user_id"], "export.items_csv")
    db.commit()

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=knowledge_items.csv"},
    )


@router.get("/items/{item_id}", response_class=HTMLResponse)
async def admin_item_detail(
    item_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    file_urls = {f.id: storage.presign_url(f.r2_key) for f in item.files}

    statuses = db.query(Status).filter(Status.is_active == True).order_by(Status.sort_order).all()

    from shared import review_ring
    return templates.TemplateResponse("admin/item_detail.html", {
        "request": request,
        "item": item,
        "file_urls": file_urls,
        "statuses": statuses,
        "ring": review_ring(item),
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
    })


@router.post("/items/{item_id}/status")
async def admin_change_status(
    item_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    status_id: int = Form(...),
    note: str = Form(""),
):
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    new_status = db.query(Status).filter(Status.id == status_id).first()
    if not new_status:
        return RedirectResponse(f"/admin/items/{item_id}?error=Invalid status", status_code=303)

    old_status_id = item.status_id
    item.status_id = status_id
    item.updated_at = datetime.utcnow()

    db.add(StatusHistory(
        item_id=item.id,
        from_status_id=old_status_id,
        to_status_id=status_id,
        changed_by_id=session["user_id"],
        note=note.strip() or None,
    ))

    AuditLog.log(db, session["user_id"], "item.status_changed", "knowledge_item", item_id,
                 from_status=old_status_id, to_status=status_id, note=note)
    db.commit()

    # Notify Power Automate → SharePoint when an item is published
    if new_status.name == "Published":
        background_tasks.add_task(sharepoint.notify_published, item)

    return RedirectResponse(f"/admin/items/{item_id}?msg=Status updated to {new_status.name}", status_code=303)


@router.post("/items/{item_id}/lock")
async def admin_toggle_lock(
    item_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    item.is_locked = not item.is_locked
    db.commit()
    msg = "Item locked" if item.is_locked else "Item unlocked"
    return RedirectResponse(f"/admin/items/{item_id}?msg={msg}", status_code=303)


@router.post("/items/{item_id}/files/{file_id}/delete")
async def admin_delete_file(
    item_id: int,
    file_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    f = db.query(ItemFile).filter(ItemFile.id == file_id, ItemFile.item_id == item_id).first()
    if f:
        storage.delete_file(f.r2_key)
        db.delete(f)
        db.commit()

    return RedirectResponse(f"/admin/items/{item_id}?msg=File deleted", status_code=303)


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "users": users,
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
    })


@router.get("/users/new", response_class=HTMLResponse)
async def new_user_form(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse("admin/user_new.html", {
        "request": request,
        "departments": db.query(Department).order_by(Department.name).all(),
        "errors": {},
        "form": {},
    })


@router.post("/users/new")
async def create_user(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    department_id: int = Form(None),
    is_admin: bool = Form(False),
):
    errors = {}
    if not username.strip():
        errors["username"] = "Username is required."
    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."
    if not errors and db.query(User).filter(User.username == username.strip()).first():
        errors["username"] = f"Username '{username}' already exists."

    if errors:
        return templates.TemplateResponse("admin/user_new.html", {
            "request": request,
            "departments": db.query(Department).order_by(Department.name).all(),
            "errors": errors,
            "form": {"username": username, "department_id": department_id, "is_admin": is_admin},
        }, status_code=422)

    user = User(
        username=username.strip(),
        password_hash=hash_password(password),
        is_admin=is_admin,
        is_active=True,
        department_id=department_id or None,
    )
    db.add(user)
    db.flush()
    AuditLog.log(db, session["user_id"], "user.created", "user", user.id, username=username)
    db.commit()

    return RedirectResponse(f"/admin/users?msg=User {username} created", status_code=303)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    new_password: str = Form(...),
):
    if len(new_password) < 8:
        return RedirectResponse(f"/admin/users?error=Password must be at least 8 characters", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    user.password_hash = hash_password(new_password)
    AuditLog.log(db, session["user_id"], "user.password_reset", "user", user_id)
    db.commit()

    return RedirectResponse(f"/admin/users?msg=Password reset for {user.username}", status_code=303)


@router.post("/users/{user_id}/toggle")
async def toggle_user(
    user_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == session["user_id"]:
        return RedirectResponse("/admin/users?error=Cannot disable your own account", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    user.is_active = not user.is_active
    action = "user.enabled" if user.is_active else "user.disabled"
    AuditLog.log(db, session["user_id"], action, "user", user_id, username=user.username)
    db.commit()

    msg = f"User {user.username} {'enabled' if user.is_active else 'disabled'}"
    return RedirectResponse(f"/admin/users?msg={msg}", status_code=303)
