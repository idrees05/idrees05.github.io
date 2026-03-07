from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models import AuditLog, Department, DocumentType, KnowledgeItem, Source, Status, User
from shared import templates

router = APIRouter(prefix="/admin")


def _config_context(db: Session, request: Request, **extra) -> dict:
    return {
        "request": request,
        "departments": db.query(Department).order_by(Department.name).all(),
        "document_types": db.query(DocumentType).order_by(DocumentType.name).all(),
        "sources": db.query(Source).order_by(Source.name).all(),
        "statuses": db.query(Status).order_by(Status.sort_order).all(),
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
        **extra,
    }


@router.get("/config", response_class=HTMLResponse)
async def config_page(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse("admin/config.html", _config_context(db, request))


# ── Departments ───────────────────────────────────────────────────────────────

@router.post("/departments/new")
async def add_department(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/config?error=Department name is required&tab=departments", status_code=303)
    if db.query(Department).filter(Department.name == name).first():
        return RedirectResponse(f"/admin/config?error=Department '{name}' already exists&tab=departments", status_code=303)

    dept = Department(name=name)
    db.add(dept)
    db.flush()
    AuditLog.log(db, session["user_id"], "dept.created", "department", dept.id, name=name)
    db.commit()

    return RedirectResponse(f"/admin/config?msg=Department '{name}' added&tab=departments", status_code=303)


@router.post("/departments/{dept_id}/edit")
async def edit_department(
    dept_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/config?error=Department name is required&tab=departments", status_code=303)

    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    existing = db.query(Department).filter(Department.name == name, Department.id != dept_id).first()
    if existing:
        return RedirectResponse(f"/admin/config?error=Department '{name}' already exists&tab=departments", status_code=303)

    old_name = dept.name
    dept.name = name
    AuditLog.log(db, session["user_id"], "dept.renamed", "department", dept_id, old=old_name, new=name)
    db.commit()

    return RedirectResponse(f"/admin/config?msg=Department renamed to '{name}'&tab=departments", status_code=303)


@router.post("/departments/{dept_id}/delete")
async def delete_department(
    dept_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    item_count = db.query(KnowledgeItem).filter(KnowledgeItem.department_id == dept_id).count()
    user_count = db.query(User).filter(User.department_id == dept_id).count()

    if item_count > 0 or user_count > 0:
        parts = []
        if item_count:
            parts.append(f"{item_count} item{'s' if item_count != 1 else ''}")
        if user_count:
            parts.append(f"{user_count} user{'s' if user_count != 1 else ''}")
        return RedirectResponse(
            f"/admin/config?error=Cannot delete: department is used by {' and '.join(parts)}&tab=departments",
            status_code=303,
        )

    AuditLog.log(db, session["user_id"], "dept.deleted", "department", dept_id, name=dept.name)
    db.delete(dept)
    db.commit()

    return RedirectResponse("/admin/config?msg=Department deleted&tab=departments", status_code=303)


# ── Document Types ────────────────────────────────────────────────────────────

@router.post("/document-types/new")
async def add_document_type(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/config?error=Document type name is required&tab=document-types", status_code=303)
    if db.query(DocumentType).filter(DocumentType.name == name).first():
        return RedirectResponse(f"/admin/config?error=Document type '{name}' already exists&tab=document-types", status_code=303)

    dt = DocumentType(name=name)
    db.add(dt)
    db.flush()
    AuditLog.log(db, session["user_id"], "doctype.created", "document_type", dt.id, name=name)
    db.commit()

    return RedirectResponse(f"/admin/config?msg=Document type '{name}' added&tab=document-types", status_code=303)


@router.post("/document-types/{dt_id}/edit")
async def edit_document_type(
    dt_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/config?error=Document type name is required&tab=document-types", status_code=303)

    dt = db.query(DocumentType).filter(DocumentType.id == dt_id).first()
    if not dt:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    existing = db.query(DocumentType).filter(DocumentType.name == name, DocumentType.id != dt_id).first()
    if existing:
        return RedirectResponse(f"/admin/config?error=Document type '{name}' already exists&tab=document-types", status_code=303)

    old_name = dt.name
    dt.name = name
    AuditLog.log(db, session["user_id"], "doctype.renamed", "document_type", dt_id, old=old_name, new=name)
    db.commit()

    return RedirectResponse(f"/admin/config?msg=Document type renamed to '{name}'&tab=document-types", status_code=303)


@router.post("/document-types/{dt_id}/delete")
async def delete_document_type(
    dt_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    dt = db.query(DocumentType).filter(DocumentType.id == dt_id).first()
    if not dt:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    count = db.query(KnowledgeItem).filter(KnowledgeItem.document_type_id == dt_id).count()
    if count > 0:
        return RedirectResponse(
            f"/admin/config?error=Cannot delete: '{dt.name}' is used by {count} item{'s' if count != 1 else ''}&tab=document-types",
            status_code=303,
        )

    AuditLog.log(db, session["user_id"], "doctype.deleted", "document_type", dt_id, name=dt.name)
    db.delete(dt)
    db.commit()

    return RedirectResponse("/admin/config?msg=Document type deleted&tab=document-types", status_code=303)


# ── Sources ───────────────────────────────────────────────────────────────────

@router.post("/sources/new")
async def add_source(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/config?error=Source name is required&tab=sources", status_code=303)

    source = Source(name=name, description=description.strip() or None, is_active=True)
    db.add(source)
    db.flush()
    AuditLog.log(db, session["user_id"], "source.created", "source", source.id, name=name)
    db.commit()

    return RedirectResponse(f"/admin/config?msg=Source '{name}' added&tab=sources", status_code=303)


@router.post("/sources/{source_id}/edit")
async def edit_source(
    source_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
    is_active: bool = Form(True),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/config?error=Source name is required&tab=sources", status_code=303)

    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    source.name = name
    source.description = description.strip() or None
    source.is_active = is_active
    AuditLog.log(db, session["user_id"], "source.updated", "source", source_id, name=name)
    db.commit()

    return RedirectResponse(f"/admin/config?msg=Source '{name}' updated&tab=sources", status_code=303)


@router.post("/sources/{source_id}/delete")
async def delete_source(
    source_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    count = db.query(KnowledgeItem).filter(KnowledgeItem.source_id == source_id).count()
    if count > 0:
        return RedirectResponse(
            f"/admin/config?error=Cannot delete: '{source.name}' is used by {count} item{'s' if count != 1 else ''}&tab=sources",
            status_code=303,
        )

    AuditLog.log(db, session["user_id"], "source.deleted", "source", source_id, name=source.name)
    db.delete(source)
    db.commit()

    return RedirectResponse("/admin/config?msg=Source deleted&tab=sources", status_code=303)


# ── Statuses ──────────────────────────────────────────────────────────────────

@router.post("/statuses/new")
async def add_status(
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
    admin_only: bool = Form(False),
    color_class: str = Form("status-default"),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/config?error=Status name is required&tab=statuses", status_code=303)

    max_order = db.query(Status).count()
    status = Status(name=name, sort_order=max_order, admin_only=admin_only, color_class=color_class)
    db.add(status)
    db.commit()

    return RedirectResponse(f"/admin/config?msg=Status '{name}' added&tab=statuses", status_code=303)


@router.post("/statuses/{status_id}/edit")
async def edit_status(
    status_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
    admin_only: bool = Form(False),
    color_class: str = Form("status-default"),
    sort_order: int = Form(0),
    is_active: bool = Form(True),
):
    status = db.query(Status).filter(Status.id == status_id).first()
    if not status:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    status.name = name.strip()
    status.admin_only = admin_only
    status.color_class = color_class
    status.sort_order = sort_order
    status.is_active = is_active
    db.commit()

    return RedirectResponse(f"/admin/config?msg=Status updated&tab=statuses", status_code=303)


@router.post("/statuses/{status_id}/delete")
async def delete_status(
    status_id: int,
    request: Request,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    status = db.query(Status).filter(Status.id == status_id).first()
    if not status:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    count = db.query(KnowledgeItem).filter(KnowledgeItem.status_id == status_id).count()
    if count > 0:
        return RedirectResponse(
            f"/admin/config?error=Cannot delete: '{status.name}' is used by {count} item{'s' if count != 1 else ''}&tab=statuses",
            status_code=303,
        )

    db.delete(status)
    db.commit()

    return RedirectResponse("/admin/config?msg=Status deleted&tab=statuses", status_code=303)
