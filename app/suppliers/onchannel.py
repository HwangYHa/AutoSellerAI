"""온채널 (onch3.co.kr) — httpx + BeautifulSoup 스크래퍼.

검색 URL: /dbcenter_renewal/index.php?keyword=KEYWORD
상세 URL: /dbcenter_renewal/detail.php?num=ITEM_NUM
가격: 로그인 회원만 조회 가능 (비로그인 시 0 반환)
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

logger = logging.getLogger(__name__)

BASE = "https://www.onch3.co.kr"
LOGIN_URL = f"{BASE}/login/login_web.php"
SEARCH_URL = f"{BASE}/dbcenter_renewal/index.php"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT = 20


@dataclass
class OncProduct:
    source: str = "onchannel"
    source_id: str = ""
    source_url: str = ""
    name: str = ""
    supply_price: float = 0.0
    retail_price: float = 0.0
    category: str = ""
    brand: str = ""
    origin: str = "중국"
    material: str = ""
    images: list[str] = field(default_factory=list)
    detail_images: list[str] = field(default_factory=list)
    options: list[dict] = field(default_factory=list)
    stock: int = 999


_shared_client: httpx.Client | None = None
_logged_in: bool = False
_login_id_used: str = ""        # 마지막 로그인 시도 ID (설정 변경 감지용)


def reset_client() -> None:
    """설정 변경 후 로그인 세션을 초기화해 재로그인을 강제한다."""
    global _shared_client, _logged_in, _login_id_used
    if _shared_client is not None:
        try:
            _shared_client.close()
        except Exception:
            pass
    _shared_client = None
    _logged_in = False
    _login_id_used = ""


def is_logged_in() -> bool:
    return _logged_in


def _get_client() -> httpx.Client:
    """로그인 세션 클라이언트 (싱글턴, 로그인 1회 시도)."""
    global _shared_client, _logged_in, _login_id_used

    s = get_settings()
    current_id = s.onchannel_login_id.strip()

    # 설정된 ID가 바뀌면 기존 세션 폐기 후 재로그인
    if _shared_client is not None and current_id != _login_id_used:
        reset_client()

    if _shared_client is not None:
        return _shared_client

    client = httpx.Client(
        timeout=TIMEOUT,
        headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"},
        follow_redirects=True,
    )

    if current_id and s.onchannel_login_pw.strip():
        try:
            # 로그인 페이지 GET으로 쿠키 초기화
            client.get(LOGIN_URL)
            resp = client.post(LOGIN_URL, data={
                "referer_url": "/",
                "username": current_id,
                "password": s.onchannel_login_pw.strip(),
                "login": "",
            })
            # 성공 판정: 로그인 페이지를 벗어났거나 로그아웃 링크 존재
            final_url = str(resp.url)
            body_lower = resp.text.lower()
            if final_url != LOGIN_URL or "logout" in body_lower or "로그아웃" in body_lower:
                _logged_in = True
                _login_id_used = current_id
                logger.info("온채널 로그인 성공 (ID: %s)", current_id)
            else:
                _login_id_used = current_id  # 실패해도 같은 ID로 재시도 방지
                logger.warning(
                    "온채널 로그인 실패 (ID: %s) — 비로그인 모드로 검색 진행\n"
                    "  ▶ .env의 ONCHANNEL_LOGIN_ID / ONCHANNEL_LOGIN_PW 확인\n"
                    "  ▶ onch3.co.kr 에서 직접 로그인 테스트 후 동일 계정 정보 사용",
                    current_id,
                )
        except Exception as e:
            logger.debug("온채널 로그인 예외: %s", e)
            _login_id_used = current_id

    _shared_client = client
    return client


def _abs_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http"):
        return url
    return urljoin(BASE, url)


def _parse_price(text: str) -> float:
    t = re.sub(r"[^\d]", "", text)
    if t and len(t) >= 3:
        try:
            return float(t)
        except ValueError:
            pass
    return 0.0


# ── 검색 ─────────────────────────────────────────────────────────────────────

def search(keyword: str = "", category: str = "", page: int = 1, limit: int = 20) -> list[OncProduct]:
    client = _get_client()

    if keyword:
        url = f"{SEARCH_URL}?keyword={quote(keyword)}&page={page}"
    elif category:
        url = f"{SEARCH_URL}?ca_id={category}&page={page}"
    else:
        url = f"{SEARCH_URL}?page={page}"

    try:
        r = client.get(url)
        r.raise_for_status()
    except Exception as e:
        logger.error("온채널 검색 실패: %s", e)
        return []

    soup = BeautifulSoup(r.text, "lxml")
    products = []

    for item in soup.select(".product_set")[:limit]:
        prod = _parse_list_item(item)
        if prod:
            products.append(prod)

    return products


def _parse_list_item(item) -> OncProduct | None:
    link = item.select_one("a[href*='detail.php']")
    if not link:
        return None
    href = link.get("href", "")
    m = re.search(r"num=(\d+)", href)
    if not m:
        return None
    item_id = m.group(1)

    name_el = item.select_one(".product_title, dt")
    name = name_el.get_text(strip=True) if name_el else ""
    if not name:
        return None

    # 이미지 (lazy-load: data-src)
    img_el = item.select_one("img[data-src], img")
    img_url = ""
    if img_el:
        src = img_el.get("data-src") or img_el.get("src") or ""
        img_url = _abs_url(src)

    # 가격 (로그인 시 표시, 비로그인 시 0)
    price_el = item.select_one(".product_price")
    price = 0.0
    if price_el:
        price = _parse_price(price_el.get_text())

    return OncProduct(
        source_id=item_id,
        source_url=f"{BASE}/dbcenter_renewal/detail.php?num={item_id}",
        name=name,
        supply_price=price,
        retail_price=price,
        images=[img_url] if img_url else [],
    )


# ── 상품 상세 ─────────────────────────────────────────────────────────────────

def get_product(item_id: str) -> OncProduct | None:
    url = f"{BASE}/dbcenter_renewal/detail.php?num={item_id}"
    client = _get_client()
    try:
        r = client.get(url)
        r.raise_for_status()
    except Exception as e:
        logger.error("온채널 상세 수집 실패 [%s]: %s", item_id, e)
        return None

    soup = BeautifulSoup(r.text, "lxml")

    # ── 상품명: <title> 태그에서 " - 온채널" 제거
    name = ""
    if soup.title and soup.title.string:
        name = re.sub(r"\s*[-–]\s*온채널\s*$", "", soup.title.string.strip()).strip()
    if not name:
        return None

    # ── 가격: .prod_detail_box 내 .detail_page_price_3 (판매사가/공급가)
    supply_price = 0.0
    box = soup.select_one(".prod_detail_box")
    if box:
        # 헤더 행을 건너뛰고 실제 값이 있는 첫 번째 판매사가
        for el in box.select(".detail_page_price_3"):
            p = _parse_price(el.get_text())
            if p > 0:
                supply_price = p
                break
        # 판매사가 없으면 최종준수가
        if supply_price == 0:
            for el in box.select(".detail_page_price_1"):
                p = _parse_price(el.get_text())
                if p > 0:
                    supply_price = p
                    break

    # ── 대표 이미지: .prod_detail_div 내 메인 이미지 (data-src 우선)
    # 주의: .product_img 는 페이지 하단 추천상품 목록 썸네일이므로 사용 금지
    images: list[str] = []
    for img in soup.select(".prod_detail_img img, .prod_detail_imgbox img"):
        src = _abs_url(img.get("data-src") or img.get("src") or "")
        if src and src not in images and "no_img" not in src.lower() and ".svg" not in src.lower():
            images.append(src)

    # og:image 폴백 (비로그인 시 이미지 없을 때)
    if not images:
        for meta in soup.find_all("meta", attrs={"property": "og:image"}):
            src = _abs_url(meta.get("content", ""))
            if src and "no_img" not in src.lower():
                images.append(src)
                break

    # ── 상세 이미지: 상품 설명 영역 이미지
    detail_images: list[str] = []
    for sel in [".detail_content img", ".prd_desc img", ".detail_wrap img",
                ".prod_desc img", "#prod_detail img", ".item_description img"]:
        for img in soup.select(sel):
            src = _abs_url(img.get("data-src") or img.get("src") or "")
            if src and src not in images and src not in detail_images and "no_img" not in src.lower():
                detail_images.append(src)
        if detail_images:
            break

    # ── 옵션: .prod_detail_box 내 행 단위 파싱
    options: list[dict] = []
    if box:
        opt_names = [el.get_text(strip=True) for el in box.select(".detail_page_name")]
        # 첫 번째는 헤더("옵션명") → 제거
        if opt_names and opt_names[0] in ("옵션명", "옵션", ""):
            opt_names = opt_names[1:]
        # 가격
        prices_raw = [el.get_text(strip=True) for el in box.select(".detail_page_price_3")]
        if prices_raw and not _parse_price(prices_raw[0]):
            prices_raw = prices_raw[1:]  # 헤더("판매사가") 제거
        if opt_names:
            option_values = []
            for i, opt_name in enumerate(opt_names):
                price_add = 0
                if i < len(prices_raw):
                    p = _parse_price(prices_raw[i])
                    price_add = int(p - supply_price) if p > supply_price else 0
                option_values.append({"name": opt_name, "add_price": price_add})
            if option_values:
                options.append({"name": "옵션", "values": [v["name"] for v in option_values]})

    # ── 스펙 (table tr 파싱)
    origin, material, brand = "중국", "", ""
    for row in soup.select("table tr"):
        cells = row.select("th, td")
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True)
            val = cells[1].get_text(strip=True)
            if "원산지" in key:
                origin = val
            elif "소재" in key or "재질" in key:
                material = val
            elif "브랜드" in key or "제조사" in key:
                brand = val

    # ── 카테고리: 상단 카테고리 탐색
    category = ""
    for sel in [".breadcrumb a", ".path a", ".location a", ".cate_path a"]:
        bc = soup.select(sel)
        if bc:
            parts = [a.get_text(strip=True) for a in bc
                     if a.get_text(strip=True) not in ("홈", "HOME", "온채널", "전체", "")]
            if parts:
                category = " > ".join(parts)
                break

    return OncProduct(
        source_id=item_id,
        source_url=url,
        name=name,
        supply_price=supply_price,
        retail_price=supply_price,
        category=category,
        brand=brand,
        origin=origin,
        material=material,
        images=images[:5],
        detail_images=detail_images[:20],
        options=options,
    )
