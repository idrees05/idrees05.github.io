import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from database import Base, SessionLocal, engine
from models import AuditLog, Status, User
from auth import hash_password, get_session

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_STATUS_SEEDS = [
    ("Submitted",    0, False, "status-submitted"),
    ("Under Review", 1, False, "status-review"),
    ("In Progress",  2, False, "status-progress"),
    ("Rejected",     3, True,  "status-rejected"),
    ("Published",    4, True,  "status-published"),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    db = SessionLocal()
    try:
        # Seed statuses
        existing = db.query(Status).count()
        if existing == 0:
            for name, order, admin_only, color in _STATUS_SEEDS:
                db.add(Status(name=name, sort_order=order, admin_only=admin_only, color_class=color))
            db.commit()
            logger.info("Statuses seeded")

        # Seed admin user
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "changeme")
        existing_admin = db.query(User).filter(User.is_admin == True).first()
        if not existing_admin:
            admin = User(
                username=admin_username,
                password_hash=hash_password(admin_password),
                is_admin=True,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.info("Admin user created: %s", admin_username)
    except Exception as e:
        logger.error("Startup seed failed: %s", e)
    finally:
        db.close()

    yield


app = FastAPI(title="KCH Knowledge Base", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Import shared templates (sets up Jinja globals)
from shared import templates  # noqa: E402, F401

from routers import auth, app as app_router, admin, config  # noqa: E402

app.include_router(auth.router)
app.include_router(app_router.router)
app.include_router(admin.router)
app.include_router(config.router)


@app.get("/")
async def root():
    return RedirectResponse("/app", status_code=302)


@app.get("/files/{blob_name:path}")
async def serve_local_file(blob_name: str, request: Request):
    """Serve locally stored uploads (dev only — skipped when Azure Blob Storage is configured)."""
    from storage import blob_configured, local_file_path
    if blob_configured():
        raise HTTPException(status_code=404)

    session = get_session(request)
    if not session:
        raise HTTPException(status_code=303, headers={"Location": "/login"})

    path = local_file_path(blob_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404)

    # Prevent path traversal outside uploads dir
    upload_root = Path(os.getenv("LOCAL_UPLOAD_DIR", "./uploads")).resolve()
    if not str(path).startswith(str(upload_root)):
        raise HTTPException(status_code=403)

    return FileResponse(path, filename=path.name)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 303 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(exc.headers["Location"], status_code=303)
    from fastapi.responses import HTMLResponse
    if exc.status_code == 403:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "code": 403, "message": "You don't have permission to access this page."},
            status_code=403,
        )
    if exc.status_code == 404:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "code": 404, "message": "Page not found."},
            status_code=404,
        )
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
