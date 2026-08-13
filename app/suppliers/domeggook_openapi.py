"""도매꾹 공식 Open API 상품조회 클라이언트.

공식 문서 기준:
- 상품목록: getItemList v4.1
- 상품상세: getItemView v4.6

상품 조회는 Open API 범위이므로 API KEY만 필요하다.
구매/주문 등 Private API는 별도 권한 승인 및 로그인 세션을 사용한다.
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import get_settings
from app.suppliers.base import NormalizedProduct

API_BASE = "https://domeggook.com/ssl/api/"
UA = "AutoSellerAI/1.0"


def _root(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("domeggook", data) if isinstance(data, dict) else {}


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    # 수량별 차등가: 1+3800|20+3500 형태면 첫 구간 가격을 사용
    if "+" in text:
        first = text.split("|", 1)[0]
        text = first.split("+", 1)[-1]
    cleaned = re.sub(r"[^0-9.]", "", text)
    try:
        return float(cleaned or 0)
    except ValueError:
        return 0.0


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _request(params: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    if not (s.domeggook_api_key or "").strip():
        raise ValueError("DOMEEGGOOK_API_KEY가 설정되지 않았습니다.")
    payload = {"aid": s.domeggook_api_key.strip(), "om": "json", **params}
    response = httpx.get(API_BASE, params=payload, headers={"User-Agent": UA}, timeout=20)
    response.raise_for_status()
    data = response.json()
    root = _root(data)
    errors = root.get("errors") or root.get("error") or data.get("errors") or data.get("error")
    if errors:
        if isinstance(errors, dict):
            code = errors.get("code", "")
            message = errors.get("dmessage") or errors.get("message") or str(errors)
            raise ValueError(f"도매꾹 API 오류 {code}: {message}")
        raise ValueError(f"도매꾹 API 오류: {errors}")
    return root


def test_connection() -> dict[str, Any]:
    """Open API KEY를 실제 상품목록 요청으로 검증한다."""
    try:
        data = _request({
            "ver": "4.1",
            "mode": "getItemList",
            "market": "dome",
            "kw": "생활",
            "sz": 1,
            "pg": 1,
            "so": "se",
        })
        header = data.get("header") or {}
        return {
            "ok": True,
            "api": "getItemList v4.1",
            "total": _integer(header.get("numberOfItems"), 0),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def search_products(
    keyword: str,
    *,
    page: int = 1,
    limit: int = 50,
    min_price: int = 0,
    max_moq: int = 999999,
    sort: str = "se",
) -> list[NormalizedProduct]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    data = _request({
        "ver": "4.1",
        "mode": "getItemList",
        "market": "dome",
        "kw": keyword,
        "sz": min(max(int(limit), 1), 200),
        "pg": max(int(page), 1),
        "so": sort or "se",
    })
    raw = (data.get("list") or {}).get("item") or []
    if isinstance(raw, dict):
        raw = [raw]

    results: list[NormalizedProduct] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("price"))
        moq = max(1, _integer(item.get("unitQty"), 1))
        if price < float(min_price or 0) or moq > int(max_moq):
            continue
        deli = item.get("deli") if isinstance(item.get("deli"), dict) else {}
        item_no = str(item.get("no") or "").strip()
        title = str(item.get("title") or "").strip()
        if not item_no or not title:
            continue
        results.append(NormalizedProduct(
            supplier_id="domeggook",
            raw_id=item_no,
            raw_url=str(item.get("url") or f"https://domeggook.com/main/item/item_view.html?item_no={item_no}"),
            name=title,
            supply_price=price,
            retail_price=_number(item.get("priceOrg")) or price,
            moq=moq,
            stock=0,
            shipping_fee=_number(deli.get("fee")),
            lead_time_days=3,
            images=[str(item.get("thumb"))] if item.get("thumb") else [],
            detail_images=[],
            options=[],
            avg_shipping_days=3.0,
            fulfillment_rate=0.95,
            raw_data=item,
        ))
    return results


def _walk_urls(value: Any, out: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_l = str(key).lower()
            if isinstance(child, str) and child.startswith(("http://", "https://", "//")):
                if any(token in key_l for token in ("img", "image", "thumb", "photo")):
                    url = "https:" + child if child.startswith("//") else child
                    if url not in out:
                        out.append(url)
            _walk_urls(child, out)
    elif isinstance(value, list):
        for child in value:
            _walk_urls(child, out)


def _find_first(mapping: Any, keys: tuple[str, ...], default: Any = "") -> Any:
    if isinstance(mapping, dict):
        for key, value in mapping.items():
            if str(key).lower() in keys and value not in (None, "", [], {}):
                return value
        for value in mapping.values():
            found = _find_first(value, keys, None)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(mapping, list):
        for value in mapping:
            found = _find_first(value, keys, None)
            if found not in (None, "", [], {}):
                return found
    return default


def get_product(product_id: str) -> NormalizedProduct | None:
    product_id = str(product_id or "").strip()
    if not product_id:
        return None
    data = _request({
        "ver": "4.6",
        "mode": "getItemView",
        "no": product_id,
    })
    basis = data.get("basis") if isinstance(data.get("basis"), dict) else {}
    price_info = data.get("price") if isinstance(data.get("price"), dict) else {}
    qty = data.get("qty") if isinstance(data.get("qty"), dict) else {}
    deli = data.get("deli") if isinstance(data.get("deli"), dict) else {}
    dome_deli = deli.get("dome") if isinstance(deli.get("dome"), dict) else {}

    title = str(basis.get("title") or _find_first(data, ("title", "itemtitle", "subject"), "")).strip()
    if not title:
        return None

    supply_price = _number(price_info.get("dome") or price_info.get("supply"))
    resale = price_info.get("resale") if isinstance(price_info.get("resale"), dict) else {}
    retail_price = _number(resale.get("Recommand") or resale.get("recommand") or price_info.get("domeOrg")) or supply_price
    images: list[str] = []
    _walk_urls(data, images)

    return NormalizedProduct(
        supplier_id="domeggook",
        raw_id=str(basis.get("no") or product_id),
        raw_url=f"https://domeggook.com/main/item/item_view.html?item_no={product_id}",
        name=title,
        supply_price=supply_price,
        retail_price=retail_price,
        moq=max(1, _integer(qty.get("domeMoq"), 1)),
        stock=max(0, _integer(qty.get("inventory"), 0)),
        shipping_fee=_number(dome_deli.get("fee") or deli.get("fee")),
        lead_time_days=max(0, _integer(deli.get("periodDeli"), 3)),
        category=str(_find_first(data, ("category", "catename", "categoryname"), "")),
        brand=str(_find_first(data, ("brand", "brandname"), "")),
        origin=str(_find_first(data, ("origin", "country", "countryname"), "")),
        material=str(_find_first(data, ("material", "materialname"), "")),
        images=images[:10],
        detail_images=images[10:40],
        options=[],
        avg_shipping_days=float(deli.get("sendAvg") or 3.0),
        fulfillment_rate=0.95,
        raw_data=data,
    )
