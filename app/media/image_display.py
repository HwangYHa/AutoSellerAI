"""Seller OS 이미지 표시용 서버측 다운로드/캐시 유틸리티.

외부 공급처/CDN 이미지를 브라우저가 직접 요청하면 Referer/핫링크 정책 때문에
URL은 정상이어도 Streamlit에서 깨질 수 있다. UI에서는 서버가 먼저 이미지를 받아
bytes로 렌더링하고, 실패할 때만 원본 URL 렌더링 또는 placeholder로 폴백한다.

이 모듈은 DB의 원본 이미지 URL을 바꾸지 않는다.
"""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

import httpx

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
_MAX_IMAGE_BYTES = 15 * 1024 * 1024


def _referer_for(source_url: str, image_url: str) -> str:
    if source_url.startswith(("http://", "https://")):
        return source_url
    try:
        p = urlparse(image_url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}/"
    except Exception:
        pass
    return ""


@lru_cache(maxsize=512)
def fetch_display_image(image_url: str, source_url: str = "") -> bytes | None:
    """외부 이미지를 서버에서 받아 bytes로 반환한다.

    - 브라우저 UA / Accept / Referer 사용
    - redirect 허용
    - image/* Content-Type 또는 대표 이미지 magic byte 검증
    - 15MB 초과는 메모리 보호를 위해 거부
    """
    url = str(image_url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None

    headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.5",
    }
    referer = _referer_for(source_url, url)
    if referer:
        headers["Referer"] = referer

    try:
        with httpx.stream(
            "GET",
            url,
            headers=headers,
            timeout=12.0,
            follow_redirects=True,
        ) as response:
            if response.status_code != 200:
                return None
            content_type = (response.headers.get("content-type", "") or "").lower()
            total = 0
            chunks: list[bytes] = []
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > _MAX_IMAGE_BYTES:
                    return None
                chunks.append(chunk)
            data = b"".join(chunks)
            if not data:
                return None
            if content_type.startswith("image/"):
                return data
            # 일부 CDN은 application/octet-stream으로 내려준다.
            if data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"RIFF")):
                return data
    except Exception:
        return None
    return None


def clear_display_image_cache() -> None:
    fetch_display_image.cache_clear()
