"""상품 원본 이미지/상세이미지 수집 유틸리티.

공급사 API가 이미지 목록을 제공하면 그것을 우선 사용하고,
부족한 경우 raw_data 내부 HTML/URL 및 원본 상품 페이지의 이미지 태그를 보완 수집한다.

지원 태그/속성:
- img[src]
- img[data-src]
- img[data-original]
- img[data-lazy-src]
- source[srcset], img[srcset]
- og:image / twitter:image

상세 설명 영역으로 추정되는 컨테이너 안의 이미지는 detail_images로 우선 분류한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


_IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif|avif)(?:$|[?#])", re.I)
_DETAIL_HINTS = (
    "detail", "description", "content", "product-detail", "prd-detail",
    "상세", "상품설명", "goods_view", "goods-detail", "editor",
)
_THUMB_HINTS = ("thumb", "thumbnail", "small", "icon", "logo", "sprite")


@dataclass
class ImageCollection:
    images: list[str] = field(default_factory=list)
    detail_images: list[str] = field(default_factory=list)
    source: str = ""
    fetched_html: bool = False


def _normalize_url(value: str, base_url: str = "") -> str:
    v = (value or "").strip().strip('"\'')
    if not v or v.startswith(("data:", "javascript:", "blob:")):
        return ""
    # srcset은 첫 번째 후보 URL만 받는다.
    if "," in v and (" " in v or "w" in v or "x" in v):
        v = v.split(",", 1)[0].strip().split(" ", 1)[0]
    if v.startswith("//"):
        v = "https:" + v
    elif base_url:
        v = urljoin(base_url, v)
    try:
        p = urlparse(v)
        if p.scheme not in {"http", "https"}:
            return ""
    except Exception:
        return ""
    return v


def _unique(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result


def _looks_like_product_image(url: str) -> bool:
    low = url.lower()
    if any(h in low for h in ("favicon", "spacer", "loading", "blank.gif", "pixel")):
        return False
    # 확장자가 없어도 CDN 이미지 URL일 수 있으므로 지나치게 엄격하게 거르지 않는다.
    return bool(_IMAGE_EXT_RE.search(low) or "/image" in low or "img" in low or "cdn" in low)


def _container_is_detail(tag) -> bool:
    parts = [str(tag.get("id", "")), " ".join(tag.get("class", []) or [])]
    text = " ".join(parts).lower()
    return any(h.lower() in text for h in _DETAIL_HINTS)


def extract_images_from_html(html: str, base_url: str = "") -> ImageCollection:
    soup = BeautifulSoup(html or "", "lxml")
    general: list[str] = []
    detail: list[str] = []

    for meta in soup.select('meta[property="og:image"], meta[name="twitter:image"]'):
        u = _normalize_url(meta.get("content", ""), base_url)
        if u:
            general.append(u)

    for tag in soup.find_all(["img", "source"]):
        raw_values = [
            tag.get("src", ""), tag.get("data-src", ""), tag.get("data-original", ""),
            tag.get("data-lazy-src", ""), tag.get("data-echo", ""), tag.get("srcset", ""),
            tag.get("data-srcset", ""),
        ]
        parent = tag
        is_detail = False
        # 최대 5단계 상위까지 상세영역 힌트 확인
        for _ in range(5):
            if parent is None:
                break
            if getattr(parent, "attrs", None) and _container_is_detail(parent):
                is_detail = True
                break
            parent = getattr(parent, "parent", None)

        for raw in raw_values:
            u = _normalize_url(str(raw or ""), base_url)
            if not u or not _looks_like_product_image(u):
                continue
            low = u.lower()
            if any(h in low for h in _THUMB_HINTS) and not is_detail:
                # 썸네일도 대표 이미지 후보로는 남기되 뒤쪽으로 보낸다.
                general.append(u)
                continue
            (detail if is_detail else general).append(u)

    general = _unique(general)
    detail = _unique([u for u in detail if u not in set(general)])
    return ImageCollection(images=general, detail_images=detail)


def _walk_raw_for_images(value: Any, base_url: str, out_general: list[str], out_detail: list[str], key: str = "") -> None:
    key_low = key.lower()
    if isinstance(value, dict):
        for k, v in value.items():
            _walk_raw_for_images(v, base_url, out_general, out_detail, str(k))
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            _walk_raw_for_images(v, base_url, out_general, out_detail, key)
        return
    if not isinstance(value, str):
        return

    text = value.strip()
    if not text:
        return
    if "<img" in text.lower() or "<source" in text.lower():
        c = extract_images_from_html(text, base_url)
        out_general.extend(c.images)
        out_detail.extend(c.detail_images)
        return

    if any(tok in key_low for tok in ("image", "img", "thumb", "photo", "detail")):
        u = _normalize_url(text, base_url)
        if u and _looks_like_product_image(u):
            if "detail" in key_low or "description" in key_low:
                out_detail.append(u)
            else:
                out_general.append(u)


def collect_product_images(product: Any, *, fetch_page: bool = True, timeout: float = 12.0) -> ImageCollection:
    """NormalizedProduct 또는 유사 객체에서 이미지 목록을 최대한 복원한다."""
    base_url = str(getattr(product, "raw_url", "") or getattr(product, "source_url", "") or "")
    general = list(getattr(product, "images", []) or [])
    detail = list(getattr(product, "detail_images", []) or [])

    raw = getattr(product, "raw_data", {}) or {}
    _walk_raw_for_images(raw, base_url, general, detail)

    fetched = False
    if fetch_page and base_url.startswith(("http://", "https://")):
        try:
            headers = {"User-Agent": "Mozilla/5.0 AutoSellerAI/1.0"}
            r = httpx.get(base_url, headers=headers, timeout=timeout, follow_redirects=True)
            if r.status_code == 200 and "text/html" in (r.headers.get("content-type", "") or ""):
                c = extract_images_from_html(r.text, str(r.url))
                general.extend(c.images)
                detail.extend(c.detail_images)
                fetched = True
        except Exception:
            # 이미지 보완 실패가 상품 수집 전체를 실패시키면 안 된다.
            pass

    general = [_normalize_url(u, base_url) for u in general]
    detail = [_normalize_url(u, base_url) for u in detail]
    general = _unique([u for u in general if u])
    detail = _unique([u for u in detail if u and u not in set(general)])

    # 대표 이미지가 하나도 없고 상세 이미지만 있으면 첫 상세 이미지를 대표 후보로 승격
    if not general and detail:
        general = [detail[0]]
        detail = detail[1:]

    return ImageCollection(images=general, detail_images=detail, source=base_url, fetched_html=fetched)
