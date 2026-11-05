"""Password hashing, session tokens, and CSRF.

Admin sessions are server-side rows; the browser only holds an opaque random
token in an HttpOnly cookie. Tokens are stored hashed, so reading the
database does not yield usable sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import AdminSession, AdminUser

# Argon2id with the library defaults; OWASP's recommended baseline.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        _hasher.verify(stored_hash, password)
        return True
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def new_token() -> str:
    """A URL-safe random token for a session cookie."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Sessions are looked up by hash, so the raw token is never stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def create_admin_user(session: Session, username: str, password: str) -> AdminUser:
    user = AdminUser(username=username, password_hash=hash_password(password))
    session.add(user)
    session.flush()
    return user


def ensure_admin_user(session: Session) -> AdminUser | None:
    """Create the bootstrap admin when the table is empty.

    The password comes from the environment. If it is unset, no admin is
    created and the admin UI stays locked until an operator inserts one.
    """
    settings = get_settings()
    existing = session.scalar(select(AdminUser).limit(1))
    if existing is not None:
        return existing
    if not settings.admin_password:
        return None
    user = create_admin_user(session, settings.admin_username, settings.admin_password)
    session.commit()
    return user


def create_session(session: Session, user: AdminUser) -> tuple[str, AdminSession]:
    """Start a session and return (raw token, row)."""
    settings = get_settings()
    token = new_token()
    row = AdminSession(
        token_hash=hash_token(token),
        user_id=user.id,
        csrf_token=new_csrf_token(),
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    session.add(row)
    session.flush()
    return token, row


def resolve_session(session: Session, token: str | None) -> tuple[AdminUser, AdminSession] | None:
    """Look up a live session, or None when the token is missing or stale."""
    if not token:
        return None
    row = session.scalar(
        select(AdminSession).where(AdminSession.token_hash == hash_token(token))
    )
    if row is None:
        return None
    if row.expires_at <= utcnow():
        session.delete(row)
        session.commit()
        return None
    user = session.get(AdminUser, row.user_id)
    if user is None:
        session.delete(row)
        session.commit()
        return None
    return user, row


def destroy_session(session: Session, token: str | None) -> None:
    if not token:
        return
    session.execute(delete(AdminSession).where(AdminSession.token_hash == hash_token(token)))
    session.commit()


def purge_expired_sessions(session: Session) -> int:
    result = session.execute(delete(AdminSession).where(AdminSession.expires_at <= utcnow()))
    session.commit()
    return result.rowcount or 0


def verify_csrf(session_row: AdminSession, token: str | None) -> bool:
    if not token:
        return False
    return hmac.compare_digest(session_row.csrf_token, token)
