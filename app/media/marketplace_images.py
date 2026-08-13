"""판매채널 API 이미지 경로를 브라우저가 표시할 수 있는 URL로 정규화한다.

쿠팡 상품조회 API의 ``cdnPath`` 는 종종
``vendor_inventory/images/...`` 형태의 CDN 상대 경로로 반환된다.
이 값을 그대로 Streamlit ``st.image`` 에 넘기면 깨진 이미지가 표시된다.

이 모듈은 플랫폼 응답을 DB에 저장하기 전에 완전한 URL로 바꾸고,
이미 저장된 레거시 값도 화면/복구 작업에서 안전하게 해석한다.
"""
from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse

from app.media.product_images import extract_images_from_html

COUPANG_CDN_BASE = "https://image11.coupangcdn.com/image/"


def _clean(value: object) -> str:
    return str(value or "").strip().strip('"\'')


def is_http_image_url(value: object) -> bool:
    """브라우저에서 직접 표시 가능한 http(s) URL인지 확인한다."""
    v = _clean(value)
    if v.startswith("//"):
        v = "https:" + v
    try:
        parsed = urlparse(v)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_image_url(value: object, *, platform: str = "") -> str:
    """단일 이미지 경로를 완전한 URL로 변환한다.

    - 이미 http(s) URL이면 그대로 사용하되 Coupang CDN http는 https로 승격한다.
    - ``//host/path`` 는 https URL로 변환한다.
    - 쿠팡 ``cdnPath`` 상대경로는 Coupang CDN 절대 URL로 변환한다.
    - 파일명 하나뿐인 vendorPath 등 출처를 복원할 수 없는 값은 버린다.
    """
    v = _clean(value)
    if not v or v.startswith(("data:", "blob:", "javascript:")):
        return ""
    if v.startswith("//"):
        v = "https:" + v
    if v.startswith("http://") and "coupangcdn.com" in v.lower():
        v = "https://" + v[len("http://"):]
    if is_http_image_url(v):
        return v

    if platform.lower() == "coupang":
        path = v.lstrip("/")
        # 상품조회 API cdnPath의 대표적인 두 형태를 지원한다.
        if path.startswith(("vendor_inventory/", "product/", "image/")):
            if path.startswith("image/"):
                path = path[len("image/"):]
            return COUPANG_CDN_BASE + path

    return ""


def _dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def normalize_image_list(values: Iterable[object] | None, *, platform: str = "") -> list[str]:
    return _dedupe(
        normalize_image_url(v, platform=platform)
        for v in (values or [])
    )


def _coupang_image_entry_url(image: dict) -> str:
    """쿠팡 이미지 객체에서 가장 신뢰할 수 있는 표시 URL을 고른다."""
    vendor = normalize_image_url(image.get("vendorPath"), platform="coupang")
    if vendor:
        return vendor
    return normalize_image_url(image.get("cdnPath"), platform="coupang")


def extract_coupang_product_images(detail: dict) -> tuple[list[str], list[str]]:
    """쿠팡 상품 상세 응답에서 대표/상세 이미지를 분리해 완전 URL로 반환한다."""
    reps: list[str] = []
    details: list[str] = []

    for option in detail.get("items") or []:
        images = option.get("images") or []
        if isinstance(images, dict):
            images = [images]
        images = sorted(
            (x for x in images if isinstance(x, dict)),
            key=lambda x: int(x.get("imageOrder") or 0),
        )
        for image in images:
            url = _coupang_image_entry_url(image)
            if not url:
                continue
            image_type = str(image.get("imageType") or "").upper()
            if image_type == "REPRESENTATION":
                reps.append(url)
            else:
                details.append(url)

        # 상품 상세 컨텐츠에는 실제 Coupang CDN 절대 URL이 포함되는 경우가 많다.
        for content_group in option.get("contents") or []:
            for content_detail in content_group.get("contentDetails") or []:
                raw = _clean(content_detail.get("content"))
                if not raw:
                    continue
                if "<img" in raw.lower() or "<source" in raw.lower():
                    extracted = extract_images_from_html(raw)
                    details.extend(extracted.images)
                    details.extend(extracted.detail_images)
                else:
                    # HTML이 아닌 URL 문자열인 경우도 처리한다.
                    for candidate in re.findall(r"https?://[^\s\"'<>]+", raw):
                        url = normalize_image_url(candidate, platform="coupang")
                        if url:
                            details.append(url)

    reps = _dedupe(reps)
    details = _dedupe(url for url in details if url not in set(reps))
    if not reps and details:
        reps = [details.pop(0)]
    return reps, details


def first_display_image(values: Iterable[object] | None, *, source: str = "") -> str:
    """DB Product.images에서 UI 대표이미지 하나를 안전하게 반환한다."""
    platform = "coupang" if source in {"coupang", "coupang_import"} else ""
    normalized = normalize_image_list(values, platform=platform)
    return normalized[0] if normalized else ""
