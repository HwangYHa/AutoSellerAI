"""온채널 (onch3.co.kr) — httpx + BeautifulSoup 스크래퍼.

검색 URL: /dbcenter_renewal/index.php?keyword=KEYWORD
상세 URL: /dbcenter_renewal/detail.php?num=ITEM_NUM
가격: 로그인 회원만 조회 가능 (비로그인 시 0 반환)

이미지/상세페이지 재수집도 반드시 동일 로그인 세션을 재사용한다.
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
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
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
_login_id_used: str = ""


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

    if _shared_client is not None and current_id != _login_id_used:
        reset_client()

    if _shared_client is not None:
        return _shared_client

    client = httpx.Client(
        timeout=TIMEOUT,
        headers={
            "User-Agent": UA,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.5",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        },
        follow_redirects=True,
    )

    if current_id and s.onchannel_login_pw.strip():
        try:
            client.get(LOGIN_URL)
            resp = client.post(LOGIN_URL, data={
                "referer_url": "/",
                "username": current_id,
                "password": s.onchannel_login_pw.strip(),
                "login": "",
            })
            final_url = str(resp.url)
            body_lower = resp.text.lower()
            if final_url != LOGIN_URL or "logout" in body_lower or "로그아웃" in body_lower:
                _logged_in = True
                _login_id_used = current_id
                logger.info("온채널 로그인 성공 (ID: %s)", current_id)
            else:
                _login_id_used = current_id
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


def fetch_product_page_html(item_id: str) -> dict[str, str] | None:
    """이미지 보완 계층에서 사용할 인증된 상품 상세 HTML을 반환한다.

    일반 httpx.get을 새로 만들지 않고 판매사 로그인 쿠키가 들어있는 공용 세션을
    재사용하므로, 로그인 후에만 내려오는 상세 이미지/lazy-load 데이터도 수집할 수 있다.
    """
    item_id = str(item_id or "").strip()
    if not item_id:
        return None
    url = f"{BASE}/dbcenter_renewal/detail.php?num={item_id}"
    client = _get_client()
    try:
        response = client.get(url, headers={"Referer": SEARCH_URL})
        response.raise_for_status()
        return {"html": response.text, "url": str(response.url)}
    except Exception as exc:
        logger.warning("온채널 이미지용 상세 HTML 조회 실패 [%s]: %s", item_id, exc)
        return None


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

    img_el = item.select_one("img[data-src], img[data-original], img[data-lazy-src], img")
    img_url = ""
    if img_el:
        src = (
            img_el.get("data-src")
            or img_el.get("data-original")
            or img_el.get("data-lazy-src")
            or img_el.get("src")
            or ""
        )
        img_url = _abs_url(src)

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


def get_product(item_id: str) -> OncProduct | None:
    page = fetch_product_page_html(item_id)
    if not page:
        return None
    url = page["url"]
    soup = BeautifulSoup(page["html"], "lxml")

    name = ""
    if soup.title and soup.title.string:
        name = re.sub(r"\s*[-–]\s*온채널\s*$", "", soup.title.string.strip()).strip()
    if not name:
        return None

    supply_price = 0.0
    box = soup.select_one(".prod_detail_box")
    if box:
        for el in box.select(".detail_page_price_3"):
            p = _parse_price(el.get_text())
            if p > 0:
                supply_price = p
                break
        if supply_price == 0:
            for el in box.select(".detail_page_price_1"):
                p = _parse_price(el.get_text())
                if p > 0:
                    supply_price = p
                    break

    # 기본 선택자로 우선 수집하고, 공통 이미지 추출기가 이후 HTML 전체를 다시 보완한다.
    images: list[str] = []
    for img in soup.select(
        ".prod_detail_img img, .prod_detail_imgbox img, .prod_detail_div img, "
        "[class*='main_img'] img, [class*='main-image'] img"
    ):
        src = _abs_url(
            img.get("data-zoom-image")
            or img.get("data-original")
            or img.get("data-src")
            or img.get("src")
            or ""
        )
        if src and src not in images and "no_img" not in src.lower() and ".svg" not in src.lower():
            images.append(src)

    if not images:
        for meta in soup.find_all("meta", attrs={"property": "og:image"}):
            src = _abs_url(meta.get("content", ""))
            if src and "no_img" not in src.lower():
                images.append(src)
                break

    detail_images: list[str] = []
    for sel in [
        ".detail_content img", ".prd_desc img", ".detail_wrap img", ".prod_desc img",
        "#prod_detail img", ".item_description img", "[id*='detail'] img",
        "[class*='detail'] img", "[class*='description'] img",
    ]:
        for img in soup.select(sel):
            src = _abs_url(
                img.get("data-zoom-image")
                or img.get("data-original")
                or img.get("data-lazy-src")
                or img.get("data-src")
                or img.get("src")
                or ""
            )
            if src and src not in images and src not in detail_images and "no_img" not in src.lower():
                detail_images.append(src)

    options: list[dict] = []
    if box:
        opt_names = [el.get_text(strip=True) for el in box.select(".detail_page_name")]
        if opt_names and opt_names[0] in ("옵션명", "옵션", ""):
            opt_names = opt_names[1:]
        prices_raw = [el.get_text(strip=True) for el in box.select(".detail_page_price_3")]
        if prices_raw and not _parse_price(prices_raw[0]):
            prices_raw = prices_raw[1:]
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
        source_id=str(item_id),
        source_url=url,
        name=name,
        supply_price=supply_price,
        retail_price=supply_price,
        category=category,
        brand=brand,
        origin=origin,
        material=material,
        images=images[:10],
        detail_images=detail_images[:40],
        options=options,
    )
