"""Attachment storage.

Files are written under a private directory with generated names, so a
client can never choose a path on disk. The real filename is kept in the
database for display only.

Uploaded bytes are validated by magic number rather than by the declared
MIME type or the file extension: a client that lies about either one still
gets rejected.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

# Magic numbers for the formats the SDK is allowed to upload.
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
]

# WebP: "RIFF" .... "WEBP"
_RIFF = b"RIFF"
_WEBP = b"WEBP"

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class AttachmentError(ValueError):
    """The uploaded file is not acceptable."""


@dataclass(frozen=True)
class StoredAttachment:
    filename: str
    storage_path: str
    mime_type: str
    file_size: int
    sha256: str


def sanitize_filename(name: str | None, fallback: str = "screenshot") -> str:
    """Keep a display name safe: no path separators, no control characters."""
    if not name:
        return fallback
    base = name.replace("\\", "/").split("/")[-1].strip()
    base = _SAFE_NAME.sub("_", base)
    base = base.strip("._")
    if not base:
        return fallback
    return base[:120]


def detect_image_type(data: bytes) -> tuple[str, str]:
    """Return (mime_type, extension) based on the bytes, or raise."""
    for signature, mime, ext in _SIGNATURES:
        if data.startswith(signature):
            return mime, ext
    if len(data) >= 12 and data[:4] == _RIFF and data[8:12] == _WEBP:
        return "image/webp", ".webp"
    raise AttachmentError("只支持 JPEG / PNG / WebP 图片")


def storage_root() -> Path:
    root = get_settings().attachments_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_attachment(data: bytes, original_name: str | None) -> StoredAttachment:
    """Validate and persist one uploaded image.

    Raises AttachmentError when the bytes are not an allowed image, are
    empty, or exceed the size limit.
    """
    settings = get_settings()
    if not data:
        raise AttachmentError("附件内容为空")
    if len(data) > settings.max_attachment_bytes:
        raise AttachmentError(
            f"附件超过 {settings.max_attachment_bytes // (1024 * 1024)} MB 上限"
        )

    mime_type, ext = detect_image_type(data)

    digest = hashlib.sha256(data).hexdigest()
    # Random name on disk: the client never influences the path.
    name = f"{secrets.token_hex(16)}{ext}"
    target = storage_root() / name
    target.write_bytes(data)

    display_name = sanitize_filename(original_name, fallback=f"image{ext}")
    return StoredAttachment(
        filename=display_name,
        storage_path=str(target),
        mime_type=mime_type,
        file_size=len(data),
        sha256=digest,
    )


def delete_attachment(storage_path: str) -> None:
    """Remove a stored file; a missing file is not an error."""
    try:
        Path(storage_path).unlink(missing_ok=True)
    except OSError:
        pass


def resolve_attachment_path(storage_path: str) -> Path:
    """Return the on-disk path for a stored attachment.

    Guards against a stored path that points outside the attachment root.
    """
    root = storage_root().resolve()
    candidate = Path(storage_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise AttachmentError("附件路径非法")
    return candidate
