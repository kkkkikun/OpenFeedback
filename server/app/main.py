"""OpenFeedback application entry point.

A single FastAPI process serves the public submit API, the admin API, and
the admin web UI. One worker is deliberate: SQLite plus an in-memory rate
limiter is only correct with a single writer.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.db import Base, engine, session_scope
from app.routers import admin, public
from app.security import ensure_admin_user, purge_expired_sessions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("openfeedback")

settings = get_settings()

# The app registry. New apps are added here, or by inserting a row directly;
# no schema change is needed to onboard another app.
DEFAULT_APPS: list[dict[str, str]] = [
    {"app_id": "oit-net-portal", "name": "校园网助手", "platform": "android"},
    {"app_id": "localpixt", "name": "显影", "platform": "android"},
    {"app_id": "qianxian", "name": "牵线", "platform": "android"},
    {"app_id": "schoolwall", "name": "校园墙", "platform": "uniapp"},
]


def seed_apps() -> None:
    from sqlalchemy import select

    from app.models import App

    with session_scope() as session:
        for spec in DEFAULT_APPS:
            existing = session.scalar(select(App).where(App.app_id == spec["app_id"]))
            if existing is None:
                session.add(App(**spec))
                logger.info("registered app %s", spec["app_id"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema is created at startup for a fresh deployment; Alembic owns
    # migrations for anything that changes later.
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    seed_apps()
    with session_scope() as session:
        ensure_admin_user(session)
        purge_expired_sessions(session)
    logger.info("openfeedback started, data dir=%s", settings.data_dir)
    yield


app = FastAPI(
    title="OpenFeedback",
    version="1.0.0",
    description="多应用统一反馈服务",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.include_router(public.router)
app.include_router(admin.router)
app.include_router(admin.api)

templates = Jinja2Templates(directory="app/templates")
static_dir = Path("app/static")
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.exception_handler(413)
async def body_too_large(request: Request, exc: Exception):
    return JSONResponse(status_code=413, content={"detail": "请求体过大"})


@app.get("/", include_in_schema=False)
def root():
    return {"service": "openfeedback", "admin": "/admin", "health": "/api/v1/health"}
