"""Local media staging for Threads image posts.

Meta's Threads API accepts an image URL rather than multipart image bytes. The
Streamlit UI and social-api containers share ``./data:/app/data`` in Docker, so an
uploaded JPEG/PNG can be written once here and exposed by the social API at
``/media/threads/<filename>``. ``PUBLIC_BASE_URL`` (or the media-specific override)
must still be reachable by Meta from the public internet.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import quote, urlparse


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MEDIA_ROUTE = "/media/threads"
_ALLOWED = {
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
}


def threads_media_directory() -> Path:
    return Path(os.getenv("THREADS_MEDIA_DIR", "data/threads_media")).expanduser().resolve()


def ensure_threads_media_directory() -> Path:
    path = threads_media_directory()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _detected_type(data: bytes) -> str:
    for content_type, (_, signature) in _ALLOWED.items():
        if data.startswith(signature):
            return content_type
    return ""


def save_threads_image(filename: str, data: bytes, content_type: str = "") -> str:
    """Validate and persist one Threads image, returning the safe stored filename."""
    payload = bytes(data or b"")
    if not payload:
        raise ValueError("이미지 파일이 비어 있습니다.")
    if len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("Threads 이미지는 8MB 이하의 JPEG/PNG만 업로드할 수 있습니다.")

    detected = _detected_type(payload)
    supplied = str(content_type or "").split(";", 1)[0].strip().lower()
    if detected not in _ALLOWED:
        raise ValueError("JPEG 또는 PNG 이미지 파일만 지원합니다.")
    if supplied and supplied not in _ALLOWED:
        raise ValueError("JPEG 또는 PNG 이미지 파일만 지원합니다.")
    if supplied and supplied != detected:
        raise ValueError("파일 확장자/Content-Type과 실제 이미지 형식이 일치하지 않습니다.")

    extension = _ALLOWED[detected][0]
    digest = hashlib.sha256(payload).hexdigest()
    safe_name = f"threads-{digest[:24]}.{extension}"
    directory = ensure_threads_media_directory()
    target = directory / safe_name
    if not target.exists():
        tmp = directory / f".{safe_name}.{os.getpid()}.tmp"
        tmp.write_bytes(payload)
        os.replace(tmp, target)
    return safe_name


def threads_media_public_base() -> str:
    return (
        os.getenv("THREADS_MEDIA_PUBLIC_BASE_URL", "").strip()
        or os.getenv("PUBLIC_BASE_URL", "").strip()
        or "http://localhost:8000"
    ).rstrip("/")


def threads_media_public_url(filename: str) -> str:
    name = Path(str(filename or "")).name
    if not name or name != str(filename or ""):
        raise ValueError("invalid media filename")
    return f"{threads_media_public_base()}{MEDIA_ROUTE}/{quote(name)}"


def media_base_is_public() -> bool:
    """Best-effort guard against scheduling an image URL Meta cannot fetch."""
    parsed = urlparse(threads_media_public_base())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if host in {"localhost", "0.0.0.0", "::1"} or host.startswith("127.") or host.endswith(".local"):
        return False
    return True


__all__ = [
    "MAX_IMAGE_BYTES",
    "MEDIA_ROUTE",
    "ensure_threads_media_directory",
    "media_base_is_public",
    "save_threads_image",
    "threads_media_directory",
    "threads_media_public_base",
    "threads_media_public_url",
]
