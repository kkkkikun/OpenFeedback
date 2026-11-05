"""Request and response schemas.

The public submit endpoint accepts multipart/form-data so screenshots and
metadata travel in one request. `FeedbackPayload` is the metadata part; the
files arrive separately and are validated server-side.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FeedbackType = Literal["bug", "feature", "experience", "other"]
FeedbackStatus = Literal["NEW", "IN_PROGRESS", "RESOLVED", "CLOSED"]

VALID_TYPES: tuple[str, ...] = ("bug", "feature", "experience", "other")
VALID_STATUSES: tuple[str, ...] = ("NEW", "IN_PROGRESS", "RESOLVED", "CLOSED")

# OIT-Net-Portal's existing feedback channel uses these category names.
# Accepting them keeps the OIT migration a config change, not a rewrite.
LEGACY_TYPE_ALIASES: dict[str, str] = {
    "issue": "bug",
    "suggestion": "feature",
    "problem": "bug",
    "ux": "experience",
}


class FeedbackPayload(BaseModel):
    """The metadata part of a feedback submission."""

    app_id: str = Field(alias="appId", min_length=1, max_length=64)
    submission_id: str = Field(alias="submissionId", min_length=8, max_length=64)
    type: FeedbackType
    title: str | None = Field(default=None, max_length=255)
    description: str = Field(min_length=1, max_length=8000)
    contact: str | None = Field(default=None, max_length=255)

    app_version: str | None = Field(default=None, alias="appVersion", max_length=64)
    app_build: str | None = Field(default=None, alias="appBuild", max_length=64)
    sdk_version: str | None = Field(default=None, alias="sdkVersion", max_length=64)
    android_version: str | None = Field(default=None, alias="androidVersion", max_length=32)
    api_level: int | None = Field(default=None, alias="apiLevel", ge=1, le=99)
    manufacturer: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    locale: str | None = Field(default=None, max_length=32)
    diagnostics: str | None = Field(default=None, max_length=8000)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        key = value.strip().lower()
        return LEGACY_TYPE_ALIASES.get(key, key)

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("描述不能为空")
        return cleaned

    @field_validator("title", "contact", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    model_config = {"populate_by_name": True}


class SubmitResponse(BaseModel):
    """Returned to the client after a successful submission.

    `duplicate` is true when the same submissionId was already stored: the
    client retried after a timeout and the server did not create a second row.
    """

    ok: bool = True
    feedback_id: int
    submission_id: str
    duplicate: bool = False
    created_at: datetime


class FeedbackOut(BaseModel):
    """One row in the admin list."""

    id: int
    app_id: str
    type: str
    title: str | None
    description: str
    status: str
    created_at: datetime
    app_version: str | None
    attachment_count: int = 0

    model_config = {"from_attributes": True}


class AttachmentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    file_size: int
    created_at: datetime

    model_config = {"from_attributes": True}


class NoteOut(BaseModel):
    id: int
    content: str
    author: str
    created_at: datetime

    model_config = {"from_attributes": True}


class StatusHistoryOut(BaseModel):
    id: int
    old_status: str | None
    new_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackDetail(BaseModel):
    """Everything the admin detail page shows."""

    id: int
    app_id: str
    type: str
    title: str | None
    description: str
    contact: str | None
    status: str
    app_version: str | None
    app_build: str | None
    sdk_version: str | None
    android_version: str | None
    api_level: int | None
    manufacturer: str | None
    model: str | None
    locale: str | None
    diagnostics: str | None
    created_at: datetime
    updated_at: datetime
    attachments: list[AttachmentOut] = []
    notes: list[NoteOut] = []
    status_history: list[StatusHistoryOut] = []

    model_config = {"from_attributes": True}


class StatusUpdate(BaseModel):
    status: FeedbackStatus


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class AdminUserOut(BaseModel):
    username: str

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
