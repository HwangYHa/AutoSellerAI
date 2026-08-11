"""도매매 (domemeai.com) — REST API v1 + 웹스크래핑 폴백.

[도매매 API 구조]
  Base: https://www.domemeai.com/api
  인증: ?api_key=<DOMEMAI_API_KEY>
  검색: GET /v1/products?keyword=KEYWORD&page=1&limit=50&api_key=KEY
  상세: GET /v1/products/{product_id}?api_key=KEY

[응답 예시]
  {
    "status": "success",
    "data": {
      "products": [
        {"id": "12345", "name": "상품명", "price": 8000, "stock": 100,
         "shipping_fee": 3000, "moq": 1, "images": ["http://..."],
         "category": "생활용품", "brand": "", "origin": "중국"}
      ],
      "total": 1234
    }
  }
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BASE_API = "https://www.domemeai.com/api"
BASE_WEB = "https://www.domemeai.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT = 20


@dataclass
class DomemaiProduct:
    source: str = "domemai"
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
    stock: int = 0
    moq: int = 1
    shipping_fee: float = 3000.0


def _api_key() -> str:
    s = get_settings()
    return s.domemai_api_key or s.domeggook_api_key


def _headers() -> dict:
    return {"User-Agent": UA, "Accept": "application/json"}


def search(keyword: str, page: int = 1, limit: int = 50,
           min_price: int = 3000, moq: int = 1) -> list[DomemaiProduct]:
    """키워드로 도매매 상품을 검색한다.

    MOQ=1 필터와 최저가 필터 적용.
    API 실패 시 웹 스크래핑으로 자동 폴백.
    """
    s = get_settings()

    api_key = s.domemai_api_key or s.domeggook_api_key

    if api_key:
        try:
            return _search_api(keyword, page, limit, min_price, moq, api_key)
        except Exception as exc:
            logger.warning("도매매 API 실패, 스크래핑 폴백: %s", exc)

    return _search_scrape(keyword, page, limit, min_price, moq)


def _search_api(keyword: str, page: int, limit: int,
                min_price: int, moq: int, api_key: str) -> list[DomemaiProduct]:
    """도매매 REST API로 상품 검색."""
    params = {
        "keyword": keyword,
        "page": page,
        "limit": limit,
        "api_key": api_key,
    }
    if moq:
        params["moq"] = moq

    r = httpx.get(f"{BASE_API}/v1/products", params=params,
                  headers=_headers(), timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    products_raw = (
        data.get("data", {}).get("products", [])
        if isinstance(data.get("data"), dict)
        else data.get("products", [])
    )

    results: list[DomemaiProduct] = []
    for item in products_raw:
        price = float(item.get("price", 0) or item.get("supply_price", 0))
        if price < min_price:
            continue
        if int(item.get("moq", 1)) > moq:
            continue

        images = item.get("images", [])
        if isinstance(images, str):
            images = [images]

        results.append(DomemaiProduct(
            source="domemai",
            source_id=str(item.get("id", "")),
            source_url=f"{BASE_WEB}/product/{item.get('id', '')}",
            name=item.get("name", ""),
            supply_price=price,
            retail_price=float(item.get("retail_price", price * 2)),
            category=item.get("category", ""),
            brand=item.get("brand", ""),
            origin=item.get("origin", "중국"),
            material=item.get("material", ""),
            images=images[:10],
            detail_images=item.get("detail_images", [])[:10],
            options=item.get("options", []),
            stock=int(item.get("stock", 0)),
            moq=int(item.get("moq", 1)),
            shipping_fee=float(item.get("shipping_fee", 3000)),
        ))

    return results


def _search_scrape(keyword: str, page: int, limit: int,
                   min_price: int, moq: int) -> list[DomemaiProduct]:
    """웹 스크래핑으로 도매매 상품 검색 (API 불가 시 폴백)."""
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import quote

        url = f"{BASE_WEB}/search?q={quote(keyword)}&page={page}&per_page={limit}"
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            logger.warning("도매매 스크래핑 HTTP %s", r.status_code)
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        # 상품 카드 선택자 (도매매 실제 구조에 맞게 조정 필요)
        cards = (
            soup.select(".product-item")
            or soup.select(".goods-item")
            or soup.select("[class*='product']")
        )

        results: list[DomemaiProduct] = []
        for card in cards[:limit]:
            try:
                name_el = card.select_one(".product-name, .goods-name, h3, h4")
                price_el = card.select_one(".price, .product-price, [class*='price']")
                img_el = card.select_one("img")
                link_el = card.select_one("a[href]")

                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    continue

                price_text = price_el.get_text(strip=True) if price_el else "0"
                import re
                nums = re.findall(r"[\d,]+", price_text)
                price = float(nums[0].replace(",", "")) if nums else 0
                if price < min_price:
                    continue

                src = img_el.get("src", "") if img_el else ""
                if src and not src.startswith("http"):
                    src = BASE_WEB + src

                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = BASE_WEB + href

                import re as _re
                match_id = _re.search(r"/(?:product|goods)/(\d+)", href)
                source_id = match_id.group(1) if match_id else ""

                results.append(DomemaiProduct(
                    source="domemai",
                    source_id=source_id,
                    source_url=href,
                    name=name,
                    supply_price=price,
                    images=[src] if src else [],
                ))
            except Exception:
                continue

        return results

    except Exception as exc:
        logger.error("도매매 스크래핑 실패: %s", exc)
        return []


def get_product(product_id: str) -> DomemaiProduct | None:
    """도매매 상품 상세 조회."""
    s = get_settings()
    api_key = s.domemai_api_key or s.domeggook_api_key

    if api_key:
        try:
            return _get_product_api(product_id, api_key)
        except Exception as exc:
            logger.warning("도매매 상세 API 실패, 스크래핑 폴백: %s", exc)

    return _get_product_scrape(product_id)


def _get_product_api(product_id: str, api_key: str) -> DomemaiProduct | None:
    r = httpx.get(
        f"{BASE_API}/v1/products/{product_id}",
        params={"api_key": api_key},
        headers=_headers(),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    item = data.get("data") or data.get("product") or data

    if not item or not item.get("name"):
        return None

    price = float(item.get("price", 0) or item.get("supply_price", 0))
    images = item.get("images", [])
    if isinstance(images, str):
        images = [images]

    options_raw = item.get("options", [])
    if isinstance(options_raw, list) and options_raw and isinstance(options_raw[0], str):
        options_raw = [{"name": "옵션", "values": options_raw}]

    return DomemaiProduct(
        source="domemai",
        source_id=str(product_id),
        source_url=f"{BASE_WEB}/product/{product_id}",
        name=item.get("name", ""),
        supply_price=price,
        retail_price=float(item.get("retail_price", price * 2)),
        category=item.get("category", ""),
        brand=item.get("brand", ""),
        origin=item.get("origin", "중국"),
        material=item.get("material", ""),
        images=images[:10],
        detail_images=item.get("detail_images", [])[:10],
        options=options_raw,
        stock=int(item.get("stock", 0)),
        moq=int(item.get("moq", 1)),
        shipping_fee=float(item.get("shipping_fee", 3000)),
    )


def _get_product_scrape(product_id: str) -> DomemaiProduct | None:
    """도매매 상품 상세 스크래핑."""
    try:
        from bs4 import BeautifulSoup
        import re

        url = f"{BASE_WEB}/product/{product_id}"
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        name_el = soup.select_one("h1.product-name, .product-title, h1")
        price_el = soup.select_one(".sale-price, .product-price, [class*='price']")
        imgs = soup.select(".product-image img, .gallery img")

        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            return None

        price_text = price_el.get_text(strip=True) if price_el else "0"
        nums = re.findall(r"[\d,]+", price_text)
        price = float(nums[0].replace(",", "")) if nums else 0

        image_urls = []
        for img in imgs[:10]:
            src = img.get("src") or img.get("data-src", "")
            if src and not src.startswith("http"):
                src = BASE_WEB + src
            if src:
                image_urls.append(src)

        return DomemaiProduct(
            source="domemai",
            source_id=str(product_id),
            source_url=url,
            name=name,
            supply_price=price,
            images=image_urls,
        )

    except Exception as exc:
        logger.error("도매매 상세 스크래핑 실패 [%s]: %s", product_id, exc)
        return None
