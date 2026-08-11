"""쿠팡 베스트셀러 키워드 검색 스크래퍼."""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.coupang.com/",
}


@dataclass
class CoupangBestItem:
    rank: int
    name: str
    price: int
    rating: float
    review_count: int
    url: str = ""
    badge: str = ""   # "로켓배송" | "로켓직구" | ""


def get_best_items(keyword: str, limit: int = 10) -> list[CoupangBestItem]:
    """쿠팡 베스트셀러 검색 결과 수집 (최대 limit개)."""
    url = (
        f"https://www.coupang.com/np/search"
        f"?q={keyword}&sorter=bestSeller&listSize={min(limit, 36)}"
    )
    try:
        with httpx.Client(headers=_HEADERS, timeout=15, follow_redirects=True) as client:
            resp = client.get(url)

        if resp.status_code != 200:
            logger.warning("쿠팡 베스트 HTTP %s", resp.status_code)
            return []

        return _parse_search_page(resp.text, limit)

    except Exception as exc:
        logger.warning("쿠팡 베스트 수집 실패: %s", exc)
        return []


def _parse_search_page(html: str, limit: int) -> list[CoupangBestItem]:
    soup = BeautifulSoup(html, "lxml")
    product_els = soup.select("li.search-product")

    if not product_els:
        # 로그인 요청 등 비정상 응답
        logger.debug("쿠팡 검색 결과 없음 (셀렉터 미매칭)")
        return []

    results: list[CoupangBestItem] = []
    for i, el in enumerate(product_els[:limit]):
        try:
            item = _parse_item(i + 1, el)
            if item:
                results.append(item)
        except Exception:
            continue

    return results


def _parse_item(rank: int, el) -> CoupangBestItem | None:
    name_el = el.select_one(".name")
    if not name_el:
        return None

    name = name_el.get_text(strip=True)
    if not name:
        return None

    # 가격
    price_el = el.select_one(".price-value") or el.select_one(".price strong")
    price_text = price_el.get_text(strip=True).replace(",", "") if price_el else "0"
    price = int(re.sub(r"[^\d]", "", price_text) or 0)

    # 별점
    rating_el = el.select_one(".rating")
    rating_text = rating_el.get_text(strip=True) if rating_el else "0"
    try:
        rating = float(rating_text)
    except ValueError:
        rating = 0.0

    # 리뷰 수
    review_el = el.select_one(".rating-total-count")
    review_text = review_el.get_text(strip=True) if review_el else "0"
    review_num = int(re.sub(r"[^\d]", "", review_text) or 0)

    # URL
    link_el = el.select_one("a.search-product-link") or el.select_one("a[href*='/vp/products/']")
    url = f"https://www.coupang.com{link_el['href']}" if link_el and link_el.get("href") else ""

    # 배송 배지
    badge = ""
    if el.select_one(".badge-rocket"):
        badge = "로켓배송"
    elif el.select_one(".badge-rocket-global"):
        badge = "로켓직구"

    return CoupangBestItem(
        rank=rank,
        name=name,
        price=price,
        rating=rating,
        review_count=review_num,
        url=url,
        badge=badge,
    )
