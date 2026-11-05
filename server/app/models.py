"""ORM models.

The schema mirrors the plan's design: an app registry, the feedback record
itself, attachments, internal notes, and a status history. Admin users and
their sessions live here too, so the whole service is one SQLite file.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UtcDateTime, utcnow


class App(Base):
    """A registered client application."""

    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="android")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<App {self.app_id} enabled={self.enabled}>"


class Feedback(Base):
    """One submitted feedback item."""

    __tablename__ = "feedback"
    __table_args__ = (
        # The client generates submission_id; a unique constraint makes a
        # retried upload idempotent instead of creating a duplicate row.
        UniqueConstraint("app_id", "submission_id", name="uq_feedback_app_submission"),
        Index("ix_feedback_app_status_created", "app_id", "status", "created_at"),
        Index("ix_feedback_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[str] = mapped_column(String(64), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Client-supplied context. Never contains credentials by contract.
    app_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    app_build: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sdk_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    android_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    api_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(32), nullable=True)
    diagnostics: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW", index=True)

    # Hashed client IP for rate limiting; the raw address is never stored.
    client_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    attachments: Mapped[list["FeedbackAttachment"]] = relationship(
        back_populates="feedback", cascade="all, delete-orphan", lazy="selectin"
    )
    notes: Mapped[list["FeedbackNote"]] = relationship(
        back_populates="feedback", cascade="all, delete-orphan", lazy="selectin"
    )
    status_history: Mapped[list["FeedbackStatusHistory"]] = relationship(
        back_populates="feedback", cascade="all, delete-orphan", lazy="selectin"
    )


class FeedbackAttachment(Base):
    """A screenshot the user attached."""

    __tablename__ = "feedback_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey("feedback.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    feedback: Mapped["Feedback"] = relationship(back_populates="attachments")


class FeedbackNote(Base):
    """An internal note. Visible to admins only, never to the submitter."""

    __tablename__ = "feedback_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey("feedback.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(64), nullable=False, default="admin")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    feedback: Mapped["Feedback"] = relationship(back_populates="notes")


class FeedbackStatusHistory(Base):
    """Every status transition, so the admin UI can show a timeline."""

    __tablename__ = "feedback_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey("feedback.id", ondelete="CASCADE"), nullable=False, index=True
    )
    old_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)

    feedback: Mapped["Feedback"] = relationship(back_populates="status_history")


class AdminUser(Base):
    """A backend operator."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class AdminSession(Base):
    """A server-side admin session.

    The cookie carries only a random token; the token is stored hashed, so a
    database leak cannot be replayed as a live session.
    """

    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    user: Mapped["AdminUser"] = relationship()
