"""Public endpoints: submit feedback, check health.

These are the only endpoints an app talks to. They are deliberately small:
no auth is required (submission is anonymous by design), so every input is
validated and every byte counted.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import App, Feedback, FeedbackAttachment
from app.ratelimit import check_submission_rate
from app.schemas import FeedbackPayload, SubmitResponse
from app.storage import AttachmentError, save_attachment

logger = logging.getLogger("openfeedback.public")

router = APIRouter(tags=["public"])


def client_ip(request: Request) -> str:
    """The caller's address.

    Only X-Forwarded-For is consulted when the deployment explicitly trusts
    a proxy; otherwise the socket address is used, so a client cannot spoof
    its way past the rate limit.
    """
    if get_settings().trusted_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


@router.get("/api/v1/health")
def health() -> dict[str, object]:
    """Liveness probe. Deliberately does not touch the database."""
    return {"status": "ok", "service": "openfeedback"}


@router.post("/api/v1/feedback", response_model=SubmitResponse)
async def submit_feedback(
    request: Request,
    payload_json: str = Form(..., alias="payload"),
    attachments: list[UploadFile] = File(default_factory=list),
    session: Session = Depends(get_db),
) -> SubmitResponse:
    """Accept one feedback item, optionally with screenshots.

    The metadata arrives as a JSON string in the `payload` form field so the
    same endpoint serves the Android SDK, the uni-app component, and the
    Rust client without a second route.
    """
    settings = get_settings()

    try:
        raw = json.loads(payload_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="payload 不是合法 JSON")

    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="payload 必须是 JSON 对象")

    try:
        payload = FeedbackPayload.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError
        raise HTTPException(status_code=422, detail=f"参数不合法: {_first_error(exc)}")

    app_row = session.scalar(select(App).where(App.app_id == payload.app_id))
    if app_row is None:
        raise HTTPException(status_code=404, detail="未知 appId")
    if not app_row.enabled:
        raise HTTPException(status_code=403, detail="该应用已停用接收反馈")

    ip = client_ip(request)
    if not check_submission_rate(payload.app_id, ip):
        raise HTTPException(status_code=429, detail="提交过于频繁，请稍后再试")

    if len(attachments) > settings.max_attachments:
        raise HTTPException(
            status_code=422, detail=f"最多只能上传 {settings.max_attachments} 张截图"
        )

    # A retry of the same submissionId must not create a second row.
    existing = session.scalar(
        select(Feedback).where(
            Feedback.app_id == payload.app_id,
            Feedback.submission_id == payload.submission_id,
        )
    )
    if existing is not None:
        return SubmitResponse(
            feedback_id=existing.id,
            submission_id=existing.submission_id,
            duplicate=True,
            created_at=existing.created_at,
        )

    saved: list = []
    try:
        for upload in attachments:
            if upload.filename == "" and not upload.file:
                continue
            data = await upload.read()
            if not data:
                continue
            saved.append(save_attachment(data, upload.filename))
    except AttachmentError as exc:
        for item in saved:
            _remove_file(item.storage_path)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        for item in saved:
            _remove_file(item.storage_path)
        raise

    feedback = Feedback(
        submission_id=payload.submission_id,
        app_id=payload.app_id,
        type=payload.type,
        title=payload.title,
        description=payload.description,
        contact=payload.contact,
        app_version=payload.app_version,
        app_build=payload.app_build,
        sdk_version=payload.sdk_version,
        android_version=payload.android_version,
        api_level=payload.api_level,
        manufacturer=payload.manufacturer,
        model=payload.model,
        locale=payload.locale,
        diagnostics=payload.diagnostics,
        status="NEW",
        client_ip_hash=_hash(ip),
        user_agent=(request.headers.get("user-agent") or "")[:255] or None,
    )
    session.add(feedback)
    session.flush()

    for item in saved:
        session.add(
            FeedbackAttachment(
                feedback_id=feedback.id,
                filename=item.filename,
                storage_path=item.storage_path,
                mime_type=item.mime_type,
                file_size=item.file_size,
                sha256=item.sha256,
            )
        )

    session.commit()

    # The content itself never reaches the log.
    logger.info(
        "feedback stored id=%s app=%s type=%s attachments=%d",
        feedback.id,
        feedback.app_id,
        feedback.type,
        len(saved),
    )

    return SubmitResponse(
        feedback_id=feedback.id,
        submission_id=feedback.submission_id,
        duplicate=False,
        created_at=feedback.created_at,
    )


def _hash(ip: str) -> str:
    from app.ratelimit import hash_ip

    return hash_ip(ip)


def _remove_file(path: str) -> None:
    from app.storage import delete_attachment

    delete_attachment(path)


def _first_error(exc: Exception) -> str:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            items = errors()
            if items:
                first = items[0]
                loc = ".".join(str(part) for part in first.get("loc", ()))
                return f"{loc}: {first.get('msg', '')}".strip(": ") or "字段不合法"
        except Exception:
            pass
    return str(exc)
