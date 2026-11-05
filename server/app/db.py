"""Database engine, session factory, and the declarative base."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, TypeDecorator, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class UtcDateTime(TypeDecorator):
    """Timestamps are stored as naive UTC and handed back as aware UTC.

    SQLite has no timezone-aware type, so an aware value would silently come
    back naive and every comparison against `now()` would be wrong.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_engine = create_engine(
    _settings.database_url,
    future=True,
    connect_args={"check_same_thread": False, "timeout": 30} if _settings.is_sqlite else {},
)

if _settings.is_sqlite:

    @event.listens_for(_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        # WAL lets a reader and a writer work at the same time, which matters
        # when the admin UI is open while a phone submits feedback.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)

# Exported under the plain name: alembic, the startup hook, and the tests all
# need the same engine instance.
engine = _engine


def get_db():
    """FastAPI dependency: one session per request.

    The return type is left unannotated on purpose. FastAPI inspects a
    dependency's annotation to build its response model, and a SQLAlchemy
    Session is not a valid Pydantic type.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and background work."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine():
    return _engine


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
