"""상품 원본 이미지/상세이미지 수집 유틸리티.

수집 우선순위
1. 공급처 API가 제공한 images/detail_images
2. raw_data 내부 이미지 필드/HTML/JSON 문자열
3. 원본 상품 페이지 HTML

지원 범위
- img/src 및 주요 lazy-load 속성
- img/source srcset의 모든 후보 중 고해상도 후보
- og:image / twitter:image
- inline style / <style>의 background-image:url(...)
- script/JSON 문자열 안의 http(s), // CDN 이미지 URL
- HTML entity, JSON escaped slash(https:\/\/...), 상대경로
- 온채널처럼 로그인 세션이 필요한 공급처의 인증 세션 HTML 재사용

원칙
- 이미지 보완 실패가 상품 수집 전체를 실패시키지는 않는다.
- 추적픽셀/파비콘/로고/placeholder 등은 최대한 제거한다.
- 원본 URL은 마켓 업로드용 데이터로 유지하고 UI 표시 문제는 별도 표시 계층에서 해결한다.
"""
from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


_IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif|avif|bmp)(?:$|[?#])", re.I)
_ABS_IMAGE_RE = re.compile(
    r"(?:(?:https?:)?//[^\s\"'<>\\]+?(?:jpe?g|png|webp|gif|avif|bmp)(?:\?[^\s\"'<>\\]*)?)",
    re.I,
)
_CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", re.I)
_DETAIL_HINTS = (
    "detail", "description", "content", "product-detail", "prd-detail",
    "goods-detail", "goods_view", "item-description", "item_description",
    "editor", "상품상세", "상세", "상품설명", "설명",
)
_BAD_HINTS = (
    "favicon", "spacer", "loading", "blank.gif", "pixel", "tracking",
    "analytics", "sprite", "icon/", "/icon", "logo", "banner/common",
)
_THUMB_HINTS = ("thumb", "thumbnail", "small", "_s.", "_80", "_100")
_IMAGE_ATTRS = (
    "src", "data-src", "data-original", "data-original-src", "data-lazy-src",
    "data-lazy", "data-echo", "data-image", "data-img", "data-url",
    "data-zoom-image", "data-large-image", "data-big", "data-pc-src",
    "data-mobile-src", "data-thumb", "data-background-image", "data-bg",
)
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


@dataclass
class ImageCollection:
    images: list[str] = field(default_factory=list)
    detail_images: list[str] = field(default_factory=list)
    source: str = ""
    fetched_html: bool = False


def _decode_text(value: object) -> str:
    v = str(value or "").strip().strip('"\'')
    if not v:
        return ""
    v = html_lib.unescape(v)
    # JSON/JS 안에서 자주 보이는 escaped URL 복원
    v = v.replace("\\/", "/")
    v = v.replace("\\u002F", "/").replace("\\u002f", "/")
    v = v.replace("\\u003A", ":").replace("\\u003a", ":")
    return v.strip()


def _normalize_url(value: object, base_url: str = "") -> str:
    v = _decode_text(value)
    if not v or v.startswith(("data:", "javascript:", "blob:", "about:")):
        return ""

    # CSS url(...) 자체가 넘어온 경우 내용만 꺼낸다.
    css_match = _CSS_URL_RE.fullmatch(v)
    if css_match:
        v = _decode_text(css_match.group(1))

    if v.startswith("//"):
        v = "https:" + v
    elif base_url:
        v = urljoin(base_url, v)

    try:
        p = urlparse(v)
    except Exception:
        return ""
    if p.scheme not in {"http", "https"} or not p.netloc:
        return ""
    return v


def _srcset_urls(value: object, base_url: str) -> list[str]:
    """srcset 전체 후보를 작은 것→큰 것 순으로 파싱한다.

    브라우저용 대표 후보는 마지막(가장 큰 descriptor) 쪽을 우선하도록 반환 순서를 뒤집는다.
    descriptor가 없더라도 모든 URL을 잃지 않는다.
    """
    text = _decode_text(value)
    if not text:
        return []
    parsed: list[tuple[float, str]] = []
    for index, part in enumerate(text.split(",")):
        bits = part.strip().split()
        if not bits:
            continue
        url = _normalize_url(bits[0], base_url)
        if not url:
            continue
        score = float(index)
        if len(bits) > 1:
            d = bits[1].lower()
            try:
                if d.endswith("w"):
                    score = float(d[:-1])
                elif d.endswith("x"):
                    score = float(d[:-1]) * 10000
            except ValueError:
                pass
        parsed.append((score, url))
    return [url for _, url in sorted(parsed, key=lambda x: x[0], reverse=True)]


def _unique(urls: Iterable[str]) -> list[str]:
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
    if any(h in low for h in _BAD_HINTS):
        return False
    # 확장자가 없는 CDN 변환 URL도 허용
    return bool(
        _IMAGE_EXT_RE.search(low)
        or "/image" in low
        or "/img" in low
        or "cdn" in low
        or "photo" in low
        or "thumbnail" in low
    )


def _container_is_detail(tag) -> bool:
    if tag is None or not getattr(tag, "attrs", None):
        return False
    parts = [
        str(tag.get("id", "")),
        " ".join(tag.get("class", []) or []),
        str(tag.get("role", "")),
        str(tag.get("data-section", "")),
    ]
    text = " ".join(parts).lower()
    return any(h.lower() in text for h in _DETAIL_HINTS)


def _is_tiny_tag(tag) -> bool:
    """명시적으로 작은 추적/아이콘 이미지만 제거한다."""
    try:
        width = int(re.sub(r"\D", "", str(tag.get("width", ""))) or 0)
        height = int(re.sub(r"\D", "", str(tag.get("height", ""))) or 0)
    except Exception:
        return False
    return bool(width and height and width <= 48 and height <= 48)


def _tag_is_detail(tag) -> bool:
    parent = tag
    for _ in range(7):
        if parent is None:
            break
        if _container_is_detail(parent):
            return True
        parent = getattr(parent, "parent", None)
    return False


def _append_candidate(url: str, *, is_detail: bool, general: list[str], detail: list[str]) -> None:
    if not url or not _looks_like_product_image(url):
        return
    if is_detail:
        detail.append(url)
    else:
        general.append(url)


def _extract_literal_urls(text: str, base_url: str = "") -> list[str]:
    """script/JSON/CSS 문자열 안의 이미지 URL을 복원한다."""
    decoded = _decode_text(text)
    if not decoded:
        return []
    results: list[str] = []

    for raw in _CSS_URL_RE.findall(decoded):
        u = _normalize_url(raw, base_url)
        if u and _looks_like_product_image(u):
            results.append(u)

    for raw in _ABS_IMAGE_RE.findall(decoded):
        u = _normalize_url(raw, base_url)
        if u and _looks_like_product_image(u):
            results.append(u)

    return _unique(results)


def extract_images_from_html(html: str, base_url: str = "") -> ImageCollection:
    soup = BeautifulSoup(html or "", "lxml")
    general: list[str] = []
    detail: list[str] = []

    # 메타 대표 이미지
    for meta in soup.select(
        'meta[property="og:image"], meta[property="og:image:url"], '
        'meta[name="twitter:image"], meta[name="twitter:image:src"]'
    ):
        u = _normalize_url(meta.get("content", ""), base_url)
        _append_candidate(u, is_detail=False, general=general, detail=detail)

    # 실제 이미지/소스 태그
    for tag in soup.find_all(["img", "source"]):
        is_detail = _tag_is_detail(tag)
        if _is_tiny_tag(tag) and not is_detail:
            continue

        candidates: list[str] = []
        for attr in _IMAGE_ATTRS:
            value = tag.get(attr)
            if value:
                candidates.append(_normalize_url(value, base_url))

        # 알려지지 않은 lazy-load 속성도 image/img/src 계열이면 보완한다.
        for attr_name, attr_value in (tag.attrs or {}).items():
            low_name = str(attr_name).lower()
            if attr_name in _IMAGE_ATTRS or low_name in {"srcset", "data-srcset", "style"}:
                continue
            if any(token in low_name for token in ("image", "img", "photo", "zoom")):
                if isinstance(attr_value, (str, int, float)):
                    candidates.append(_normalize_url(attr_value, base_url))

        srcsets: list[str] = []
        for attr in ("srcset", "data-srcset"):
            srcsets.extend(_srcset_urls(tag.get(attr, ""), base_url))
        # 고해상도 srcset 후보를 먼저 저장
        candidates = srcsets + candidates

        style = str(tag.get("style", "") or "")
        candidates.extend(_extract_literal_urls(style, base_url))

        for u in candidates:
            if not u:
                continue
            _append_candidate(u, is_detail=is_detail, general=general, detail=detail)

    # div/a/li 등의 background-image / data-image
    for tag in soup.find_all(True):
        is_detail = _tag_is_detail(tag)
        style = str(tag.get("style", "") or "")
        if style and ("url(" in style.lower() or "background" in style.lower()):
            for u in _extract_literal_urls(style, base_url):
                _append_candidate(u, is_detail=is_detail, general=general, detail=detail)
        for attr_name in ("data-background", "data-bg", "data-image", "data-original"):
            raw = tag.get(attr_name)
            if raw:
                u = _normalize_url(raw, base_url)
                _append_candidate(u, is_detail=is_detail, general=general, detail=detail)

    # style/script/JSON-LD/inline JS 안에만 있는 이미지
    for tag in soup.find_all(["style", "script"]):
        text = tag.string or tag.get_text(" ", strip=False) or ""
        if not text:
            continue
        is_detail = _tag_is_detail(tag) or "detail" in text[:500].lower()
        for u in _extract_literal_urls(text, base_url):
            _append_candidate(u, is_detail=is_detail, general=general, detail=detail)

    general = _unique(general)
    detail = _unique([u for u in detail if u not in set(general)])

    # 썸네일보다 일반/고해상도 이미지를 앞에 배치
    general.sort(key=lambda u: (any(h in u.lower() for h in _THUMB_HINTS),))
    return ImageCollection(images=general, detail_images=detail)


def _walk_raw_for_images(
    value: Any,
    base_url: str,
    out_general: list[str],
    out_detail: list[str],
    key: str = "",
) -> None:
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

    if any(marker in text.lower() for marker in ("<img", "<source", "background-image", "<picture")):
        c = extract_images_from_html(text, base_url)
        out_general.extend(c.images)
        out_detail.extend(c.detail_images)

    # 키 이름이 이미지 계열이면 상대경로도 허용
    if any(tok in key_low for tok in ("image", "img", "thumb", "photo", "picture", "detail")):
        # 문자열 자체가 srcset일 수도 있다.
        candidates = _srcset_urls(text, base_url) if "," in text else [_normalize_url(text, base_url)]
        for u in candidates:
            if u and _looks_like_product_image(u):
                if any(tok in key_low for tok in ("detail", "description", "content")):
                    out_detail.append(u)
                else:
                    out_general.append(u)

    # JSON/스크립트 값 안에 URL이 여러 개 들어있는 경우
    literals = _extract_literal_urls(text, base_url)
    if literals:
        if any(tok in key_low for tok in ("detail", "description", "content", "html")):
            out_detail.extend(literals)
        else:
            out_general.extend(literals)


def _fetch_page_html(product: Any, base_url: str, timeout: float) -> tuple[str, str]:
    """공급처 특성에 맞는 HTML을 가져온다.

    온채널은 반드시 기존 로그인 세션을 재사용한다. 그 외 공급처는 브라우저와 유사한
    헤더로 공개 상품 페이지를 조회한다.
    """
    supplier_id = str(getattr(product, "supplier_id", "") or "").lower()
    raw_id = str(getattr(product, "raw_id", "") or "")

    if supplier_id == "onchannel" and raw_id:
        try:
            from app.suppliers.onchannel import fetch_product_page_html
            page = fetch_product_page_html(raw_id)
            if page:
                return str(page.get("html", "") or ""), str(page.get("url", base_url) or base_url)
        except Exception:
            pass

    headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.5",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    response = httpx.get(base_url, headers=headers, timeout=timeout, follow_redirects=True)
    content_type = (response.headers.get("content-type", "") or "").lower()
    if response.status_code == 200 and ("text/html" in content_type or not content_type):
        return response.text, str(response.url)
    return "", str(response.url)


def collect_product_images(product: Any, *, fetch_page: bool = True, timeout: float = 15.0) -> ImageCollection:
    """NormalizedProduct 또는 유사 객체에서 대표/상세 이미지를 최대한 복원한다."""
    base_url = str(getattr(product, "raw_url", "") or getattr(product, "source_url", "") or "")
    general = list(getattr(product, "images", []) or [])
    detail = list(getattr(product, "detail_images", []) or [])

    raw = getattr(product, "raw_data", {}) or {}
    _walk_raw_for_images(raw, base_url, general, detail)

    fetched = False
    if fetch_page and base_url.startswith(("http://", "https://")):
        try:
            page_html, final_url = _fetch_page_html(product, base_url, timeout)
            if page_html:
                c = extract_images_from_html(page_html, final_url or base_url)
                general.extend(c.images)
                detail.extend(c.detail_images)
                fetched = True
                base_url = final_url or base_url
        except Exception:
            # 이미지 보완 실패가 상품 수집 전체를 실패시키면 안 된다.
            pass

    general = [_normalize_url(u, base_url) for u in general]
    detail = [_normalize_url(u, base_url) for u in detail]
    general = _unique([u for u in general if u and _looks_like_product_image(u)])
    detail = _unique([u for u in detail if u and _looks_like_product_image(u) and u not in set(general)])

    if not general and detail:
        general = [detail[0]]
        detail = detail[1:]

    return ImageCollection(
        images=general,
        detail_images=detail,
        source=base_url,
        fetched_html=fetched,
    )
