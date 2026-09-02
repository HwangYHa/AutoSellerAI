"""Cloudflare R2 publishing for generated commerce images.

Generated files remain on local disk for recovery/debugging. When R2 is enabled,
the same file is uploaded to the configured R2 bucket and the public URL is
returned to callers. When R2 is disabled, the legacy IMAGE_PUBLIC_BASE_URL
mapping is preserved without performing a network upload.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import urljoin, urlparse

import boto3
from botocore.config import Config

from app.config import get_settings


class R2PublishError(RuntimeError):
    """Raised when R2 publishing is enabled but cannot complete safely."""


def _clean_prefix(value: str) -> str:
    return "/".join(part for part in str(value or "").replace("\\", "/").split("/") if part)


def _generated_relative_path(local_path: str | Path, output_dir: str | Path) -> str:
    path = Path(local_path)
    root = Path(output_dir)
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _join_public_url(base_url: str, suffix: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return ""
    return urljoin(base + "/", str(suffix or "").lstrip("/"))


def _r2_public_url(base_url: str, object_key: str, relative_key: str, prefix: str) -> str:
    """Build a public URL without duplicating the configured object prefix.

    Both of these are valid configurations:
      IMAGE_PUBLIC_BASE_URL=https://pub-xxx.r2.dev
      IMAGE_PUBLIC_BASE_URL=https://pub-xxx.r2.dev/generated
    """
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return ""

    base_path = urlparse(base).path.strip("/")
    normalized_prefix = _clean_prefix(prefix)
    if normalized_prefix and (base_path == normalized_prefix or base_path.endswith("/" + normalized_prefix)):
        suffix = relative_key
    else:
        suffix = object_key
    return _join_public_url(base, suffix)


def _build_client(settings):
    return boto3.client(
        "s3",
        endpoint_url=str(settings.r2_endpoint).strip().rstrip("/"),
        aws_access_key_id=str(settings.r2_access_key_id).strip(),
        aws_secret_access_key=str(settings.r2_secret_access_key).strip(),
        region_name=str(settings.r2_region or "auto").strip() or "auto",
        config=Config(
            signature_version="s3v4",
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def _validate_r2_settings(settings) -> str:
    missing = [
        name
        for name, value in (
            ("R2_ACCESS_KEY_ID", settings.r2_access_key_id),
            ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
            ("R2_BUCKET", settings.r2_bucket),
            ("R2_ENDPOINT", settings.r2_endpoint),
        )
        if not str(value or "").strip()
    ]
    if missing:
        raise R2PublishError(
            "R2_ENABLED=true 이지만 필수 설정이 없습니다: " + ", ".join(missing)
        )

    public_base = str(settings.image_public_base_url or settings.image_cdn_base_url or "").strip()
    if not public_base:
        raise R2PublishError(
            "R2_ENABLED=true 이지만 IMAGE_PUBLIC_BASE_URL 또는 IMAGE_CDN_BASE_URL이 비어 있습니다. "
            "R2 공개 개발 URL(r2.dev) 또는 사용자 지정 CDN 도메인을 설정하세요."
        )
    return public_base


def publish_generated_file(local_path: str | Path) -> str:
    """Publish one generated file and return its browser-accessible URL."""
    settings = get_settings()
    path = Path(local_path)
    if not path.is_file():
        raise R2PublishError(f"업로드할 생성 이미지가 없습니다: {path}")

    relative_key = _generated_relative_path(path, settings.image_output_dir or "data/generated")
    public_base = str(settings.image_public_base_url or settings.image_cdn_base_url or "").strip()

    if not settings.r2_enabled:
        return _join_public_url(public_base, relative_key)

    public_base = _validate_r2_settings(settings)
    prefix = _clean_prefix(settings.r2_object_prefix)
    object_key = "/".join(part for part in (prefix, relative_key.lstrip("/")) if part)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    client = _build_client(settings)
    try:
        with path.open("rb") as body:
            client.put_object(
                Bucket=str(settings.r2_bucket).strip(),
                Key=object_key,
                Body=body,
                ContentType=content_type,
                CacheControl=str(settings.r2_cache_control or "").strip() or "public, max-age=31536000, immutable",
            )
    except Exception as exc:
        raise R2PublishError(
            f"Cloudflare R2 이미지 업로드 실패: {path.name} ({exc.__class__.__name__}: {exc})"
        ) from exc

    return _r2_public_url(public_base, object_key, relative_key, prefix)
