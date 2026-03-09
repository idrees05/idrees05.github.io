import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import Base, SessionLocal, engine
from importer import CSV_DIR, run_import
from models import TesterType
from routers import admin, auth, reports, results, runs, users

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # Migrate: add is_admin column to users if missing (no Alembic)
    from sqlalchemy import inspect as _inspect, text as _text
    _insp = _inspect(engine)
    _user_cols = [c["name"] for c in _insp.get_columns("users")]
    if "is_admin" not in _user_cols:
        with engine.connect() as _conn:
            _conn.execute(_text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
            _conn.commit()
        logger.info("Migrated: added is_admin column to users")
    if "force_password_change" not in _user_cols:
        with engine.connect() as _conn:
            _conn.execute(_text("ALTER TABLE users ADD COLUMN force_password_change BOOLEAN DEFAULT FALSE"))
            _conn.commit()
        logger.info("Migrated: added force_password_change column to users")

    # Run initial import
    db = SessionLocal()
    try:
        counts = run_import(db, CSV_DIR)
        logger.info(
            "Import complete: inserted=%d updated=%d deactivated=%d skipped=%d total_active=%d",
            counts["inserted"],
            counts["updated"],
            counts["deactivated"],
            counts["skipped"],
            counts.get("total_active", 0),
        )
        if counts["errors"]:
            for err in counts["errors"]:
                logger.warning("Import warning: %s", err)
    except Exception as e:
        logger.error("Import failed: %s", e)
    finally:
        db.close()

    # Seed tester types if not present
    db = SessionLocal()
    try:
        _SEED_TYPES = [
            ("everyday",   "Everyday Users",   "Standard employee — general use cases",           0),
            ("power",      "Power Users",      "Advanced functionality — complex workflows",       1),
            ("specialist", "Specialist Users", "Clinical / specialist roles — specific scenarios", 2),
        ]
        for slug, label, desc, order in _SEED_TYPES:
            if not db.get(TesterType, slug):
                db.add(TesterType(slug=slug, label=label, description=desc, sort_order=order))
        db.commit()
        logger.info("Tester types seeded/verified")
    except Exception as e:
        logger.error("Tester type seed failed: %s", e)
    finally:
        db.close()

    # Ensure upload dir exists
    Path(os.getenv("UPLOAD_DIR", "./uploads")).mkdir(parents=True, exist_ok=True)

    yield


app = FastAPI(title="KCH UAT Test Runner", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

from shared import templates

app.include_router(auth.router)
app.include_router(runs.router)
app.include_router(results.router)
app.include_router(admin.router)
app.include_router(reports.router)
app.include_router(users.router)


@app.exception_handler(303)
async def redirect_303_handler(request: Request, exc):
    return RedirectResponse(exc.headers["Location"], status_code=303)


# HTTPException with status 303 used for auth redirects
from fastapi import HTTPException

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 303 and "Location" in (exc.headers or {}):
        return RedirectResponse(exc.headers["Location"], status_code=303)
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
