"""Admin API and admin web UI.

Every admin route requires a live session. Mutating routes additionally
require the CSRF token that was issued with that session, which the UI
sends back in the `X-CSRF-Token` header or as a hidden form field.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import (
    AdminSession,
    AdminUser,
    App,
    Feedback,
    FeedbackNote,
    FeedbackStatusHistory,
)
from app.ratelimit import check_login_rate
from app.schemas import (
    FeedbackDetail,
    FeedbackOut,
    LoginRequest,
    NoteCreate,
    NoteOut,
    StatusUpdate,
    SubmitResponse,
)
from app.security import (
    create_session,
    destroy_session,
    resolve_session,
    verify_csrf,
    verify_password,
)

router = APIRouter(tags=["admin"])
api = APIRouter(prefix="/api/v1/admin", tags=["admin-api"])

templates = Jinja2Templates(directory="app/templates")
settings = get_settings()

PAGE_SIZE = 25


# --------------------------------------------------------------------------
# session helpers
# --------------------------------------------------------------------------
def current_session(request: Request, session: Session):
    """Resolve the caller's session, or None."""
    token = request.cookies.get(settings.cookie_name)
    return resolve_session(session, token)


def require_admin(request: Request, session: Session = Depends(get_db)):
    resolved = current_session(request, session)
    if resolved is None:
        raise HTTPException(status_code=401, detail="需要登录")
    return resolved


def require_admin_api(
    request: Request,
    session: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    """Dependency for mutating admin API routes."""
    resolved = require_admin(request, session)
    if not verify_csrf(resolved[1], x_csrf_token):
        raise HTTPException(status_code=403, detail="CSRF 校验失败")
    return resolved


# --------------------------------------------------------------------------
# admin API
# --------------------------------------------------------------------------
@api.post("/login")
def api_login(
    request: Request,
    body: LoginRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    ip = request.client.host if request.client else "0.0.0.0"
    if not check_login_rate(ip):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")

    user = session.scalar(select(AdminUser).where(AdminUser.username == body.username))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token, row = create_session(session, user)
    user.last_login_at = datetime.now(timezone.utc)
    session.commit()

    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"ok": True, "username": user.username, "csrfToken": row.csrf_token}


@api.post("/logout")
def api_logout(request: Request, session: Session = Depends(get_db)) -> dict[str, bool]:
    destroy_session(session, request.cookies.get(settings.cookie_name))
    response = Response()
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}


@api.get("/session")
def api_session(request: Request, session: Session = Depends(get_db)) -> dict[str, object]:
    resolved = current_session(request, session)
    if resolved is None:
        raise HTTPException(status_code=401, detail="需要登录")
    user, row = resolved
    return {"username": user.username, "csrfToken": row.csrf_token}


@api.get("/apps")
def api_apps(_=Depends(require_admin), session: Session = Depends(get_db)) -> list[dict]:
    rows = session.scalars(select(App).order_by(App.app_id)).all()
    return [
        {"appId": row.app_id, "name": row.name, "platform": row.platform, "enabled": row.enabled}
        for row in rows
    ]


@api.get("/feedback", response_model=list[FeedbackOut])
def api_feedback_list(
    app_id: str | None = Query(default=None, alias="appId"),
    status: str | None = None,
    type: str | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    session: Session = Depends(get_db),
    _=Depends(require_admin),
) -> list[FeedbackOut]:
    stmt = select(Feedback)
    count_stmt = select(func.count(Feedback.id))

    if app_id:
        stmt = stmt.where(Feedback.app_id == app_id)
        count_stmt = count_stmt.where(Feedback.app_id == app_id)
    if status:
        stmt = stmt.where(Feedback.status == status)
        count_stmt = count_stmt.where(Feedback.status == status)
    if type:
        stmt = stmt.where(Feedback.type == type)
        count_stmt = count_stmt.where(Feedback.type == type)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Feedback.title.ilike(pattern), Feedback.description.ilike(pattern))
        )
        count_stmt = count_stmt.where(
            or_(Feedback.title.ilike(pattern), Feedback.description.ilike(pattern))
        )

    total = session.scalar(count_stmt) or 0
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, pages)

    stmt = (
        stmt.order_by(Feedback.created_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    )
    rows = session.scalars(stmt).all()
    return [
        FeedbackOut(
            id=row.id,
            app_id=row.app_id,
            submission_id=row.submission_id,
            type=row.type,
            title=row.title,
            description=row.description,
            status=row.status,
            created_at=row.created_at,
            app_version=row.app_version,
            attachment_count=len(row.attachments),
        )
        for row in rows
    ]


@api.get("/feedback/{feedback_id}", response_model=FeedbackDetail)
def api_feedback_detail(
    feedback_id: int,
    session: Session = Depends(get_db),
    _=Depends(require_admin),
) -> FeedbackDetail:
    row = session.get(Feedback, feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    return FeedbackDetail(
        id=row.id,
        app_id=row.app_id,
        submission_id=row.submission_id,
        type=row.type,
        title=row.title,
        description=row.description,
        contact=row.contact,
        status=row.status,
        app_version=row.app_version,
        app_build=row.app_build,
        sdk_version=row.sdk_version,
        android_version=row.android_version,
        api_level=row.api_level,
        manufacturer=row.manufacturer,
        model=row.model,
        locale=row.locale,
        diagnostics=row.diagnostics,
        created_at=row.created_at,
        updated_at=row.updated_at,
        attachments=[
            {
                "id": a.id,
                "filename": a.filename,
                "mime_type": a.mime_type,
                "file_size": a.file_size,
                "created_at": a.created_at,
            }
            for a in row.attachments
        ],
        notes=[
            {"id": n.id, "content": n.content, "author": n.author, "created_at": n.created_at}
            for n in row.notes
        ],
        status_history=[
            {
                "id": h.id,
                "old_status": h.old_status,
                "new_status": h.new_status,
                "created_at": h.created_at,
            }
            for h in row.status_history
        ],
    )


@api.patch("/feedback/{feedback_id}")
def api_update_status(
    feedback_id: int,
    body: StatusUpdate,
    session: Session = Depends(get_db),
    resolved=Depends(require_admin_api),
) -> dict[str, object]:
    row = session.get(Feedback, feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    old_status = row.status
    if old_status != body.status:
        row.status = body.status
        session.add(
            FeedbackStatusHistory(
                feedback_id=row.id, old_status=old_status, new_status=body.status
            )
        )
        session.commit()
    return {"ok": True, "status": row.status}


@api.post("/feedback/{feedback_id}/notes", response_model=NoteOut)
def api_add_note(
    feedback_id: int,
    body: NoteCreate,
    session: Session = Depends(get_db),
    resolved=Depends(require_admin_api),
) -> NoteOut:
    row = session.get(Feedback, feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    user = resolved[0]
    note = FeedbackNote(
        feedback_id=row.id, content=body.content.strip(), author=user.username
    )
    session.add(note)
    session.commit()
    return NoteOut(
        id=note.id,
        content=note.content,
        author=note.author,
        created_at=note.created_at,
    )


@api.get("/attachments/{attachment_id}")
def api_attachment(
    attachment_id: int,
    session: Session = Depends(get_db),
    _=Depends(require_admin),
) -> Response:
    """Serve an attachment. Only reachable with a valid admin session."""
    from app.models import FeedbackAttachment
    from app.storage import AttachmentError, resolve_attachment_path

    row = session.get(FeedbackAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    try:
        path = resolve_attachment_path(row.storage_path)
    except AttachmentError:
        raise HTTPException(status_code=404, detail="附件不存在")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="附件不存在")
    return Response(
        content=path.read_bytes(),
        media_type=row.mime_type,
        headers={"Content-Disposition": f'inline; filename="{row.filename}"'},
    )


# --------------------------------------------------------------------------
# admin web UI
# --------------------------------------------------------------------------
@router.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    app_id: str | None = None,
    status: str | None = None,
    type: str | None = None,
    q: str | None = None,
    page: int = 1,
    session: Session = Depends(get_db),
):
    resolved = current_session(request, session)
    if resolved is None:
        return RedirectResponse("/admin/login", status_code=303)

    user, row = resolved
    stmt = select(Feedback)
    if app_id:
        stmt = stmt.where(Feedback.app_id == app_id)
    if status:
        stmt = stmt.where(Feedback.status == status)
    if type:
        stmt = stmt.where(Feedback.type == type)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Feedback.title.ilike(pattern), Feedback.description.ilike(pattern))
        )

    total = session.scalar(select(func.count(Feedback.id))) or 0
    items = session.scalars(
        stmt.order_by(Feedback.created_at.desc())
        .offset((max(1, page) - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()

    stats = {
        row_status: session.scalar(
            select(func.count(Feedback.id)).where(Feedback.status == row_status)
        )
        or 0
        for row_status in ("NEW", "IN_PROGRESS", "RESOLVED", "CLOSED")
    }
    per_app = {
        a.app_id: a.count
        for a in session.execute(
            select(Feedback.app_id, func.count(Feedback.id).label("count")).group_by(
                Feedback.app_id
            )
        ).all()
    }

    apps = session.scalars(select(App).order_by(App.name)).all()

    return templates.TemplateResponse(
        request,
        "admin_list.html",
        {
            "user": user,
            "csrf_token": row.csrf_token,
            "items": items,
            "stats": stats,
            "total": total,
            "per_app": per_app,
            "apps": apps,
            "filters": {"app_id": app_id, "status": status, "type": type, "q": q},
            "page": page,
            "page_size": PAGE_SIZE,
        },
    )


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request, session: Session = Depends(get_db)):
    if current_session(request, session) is not None:
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(request, "admin_login.html", {"error": None})


@router.post("/admin/login")
def admin_login_submit(
    request: Request,
    # 必须声明成 Form：写成普通 str 的话 FastAPI 会当成查询参数，
    # 于是 POST 的表单体被整个忽略，登录永远返回「用户名或密码错误」。
    username: str = Form(""),
    password: str = Form(""),
    session: Session = Depends(get_db),
):
    ip = request.client.host if request.client else "0.0.0.0"
    if not check_login_rate(ip):
        return templates.TemplateResponse(
            request, "admin_login.html", {"error": "登录尝试过于频繁，请稍后再试"}, status_code=429
        )

    user = session.scalar(select(AdminUser).where(AdminUser.username == username))
    if user is None or not verify_password(user.password_hash, password):
        return templates.TemplateResponse(
            request, "admin_login.html", {"error": "用户名或密码错误"}, status_code=401
        )

    token, row = create_session(session, user)
    user.last_login_at = datetime.now(timezone.utc)
    session.commit()

    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/admin/logout")
def admin_logout(request: Request, session: Session = Depends(get_db)):
    destroy_session(session, request.cookies.get(settings.cookie_name))
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(settings.cookie_name, path="/")
    return response


@router.get("/admin/feedback/{feedback_id}", response_class=HTMLResponse)
def admin_feedback_detail(
    feedback_id: int,
    request: Request,
    session: Session = Depends(get_db),
):
    resolved = current_session(request, session)
    if resolved is None:
        return RedirectResponse("/admin/login", status_code=303)
    user, row = resolved
    item = session.get(Feedback, feedback_id)
    if item is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    return templates.TemplateResponse(
        request,
        "admin_detail.html",
        {"user": user, "csrf_token": row.csrf_token, "item": item},
    )
