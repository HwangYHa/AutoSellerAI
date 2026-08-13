"""판매채널에 이미 등록된 상품을 로컬 DB로 역동기화한다.

AutoSellerAI를 통하지 않고 쿠팡 Wing 또는 네이버 스마트스토어 판매자센터에서
직접 등록/수정한 상품도 내부 상품관리·SEO 기능에서 사용할 수 있도록 읽어 온다.
플랫폼에는 쓰기 작업을 하지 않는다.

동기화 원칙
1. 동일 platform/platform_id Listing이 있으면 외부 상품명·판매가·이미지 등 변경사항을 갱신한다.
2. Listing은 없지만 IMPORT-{platform}-{platform_id} 상품이 있으면 다시 연결한다.
3. 이름이 같은 로컬 상품이 있고 해당 플랫폼 Listing이 없으면 그 상품에 연결한다.
4. 나머지는 source={platform}_import 신규 Product로 만든다.
5. 판매채널 API의 상대 이미지 경로는 DB에 저장하기 전에 브라우저 표시 가능한 절대 URL로 정규화한다.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.db import Listing, Product, get_db
from app.media.marketplace_images import (
    extract_coupang_product_images,
    normalize_image_list,
    normalize_image_url,
)
from app.seo.duplicate_detector import _normalize

logger = logging.getLogger(__name__)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _item_images(item: dict, platform: str) -> tuple[list[str], list[str]]:
    """신/구 카탈로그 아이템 포맷을 모두 지원한다."""
    images = item.get("images")
    if not isinstance(images, list):
        image = item.get("image")
        images = [image] if image else []
    details = item.get("detail_images")
    if not isinstance(details, list):
        details = []
    return (
        normalize_image_list(images, platform=platform),
        normalize_image_list(details, platform=platform),
    )


def _find_or_link_product(
    db,
    platform: str,
    platform_id: str,
    item: dict,
) -> tuple[Product, bool]:
    """Returns (product, created)."""
    name = str(item.get("name", "") or "").strip()
    price = _number(item.get("price"))
    sku = f"IMPORT-{platform}-{platform_id}"[:120]

    existing = db.query(Product).filter_by(sku=sku).first()
    if existing:
        return existing, False

    target_key = _normalize(name)[:30]
    if target_key:
        for candidate in db.query(Product).all():
            if _normalize(candidate.name)[:30] != target_key:
                continue
            already_linked = db.query(Listing).filter_by(
                product_id=candidate.id, platform=platform, status="success"
            ).first()
            if not already_linked:
                return candidate, False

    images, detail_images = _item_images(item, platform)
    product = Product(
        sku=sku,
        source=f"{platform}_import",
        source_id=platform_id,
        name=name[:300],
        supply_price=0.0,
        sell_price=price,
        category=str(item.get("category", "") or "")[:200],
        brand=str(item.get("brand", "") or "")[:120],
        images=json.dumps(images, ensure_ascii=False),
        detail_images=json.dumps(detail_images, ensure_ascii=False),
        status="listed",
    )
    db.add(product)
    db.flush()
    return product, True


def _apply_external_fields(product: Product, item: dict, platform: str) -> bool:
    """판매자센터에서 바뀐 사용자 노출 필드를 로컬 Product에 반영한다."""
    changed = False

    name = str(item.get("name", "") or "").strip()
    if name and product.name != name[:300]:
        product.name = name[:300]
        changed = True

    price = _number(item.get("price"))
    if price > 0 and abs(float(product.sell_price or 0) - price) > 0.01:
        product.sell_price = price
        changed = True

    category = str(item.get("category", "") or "").strip()
    if category and product.category != category[:200]:
        product.category = category[:200]
        changed = True

    brand = str(item.get("brand", "") or "").strip()
    if brand and product.brand != brand[:120]:
        product.brand = brand[:120]
        changed = True

    images, details = _item_images(item, platform)
    if images:
        images_json = json.dumps(images, ensure_ascii=False)
        if product.images != images_json:
            product.images = images_json
            changed = True
    if details:
        details_json = json.dumps(details, ensure_ascii=False)
        if product.detail_images != details_json:
            product.detail_images = details_json
            changed = True

    if product.status != "listed":
        product.status = "listed"
        changed = True

    return changed


def _sync(platform: str, items: list[dict]) -> dict:
    created = linked = updated = skipped = 0

    with get_db() as db:
        for item in items:
            platform_id = str(item.get("platform_id", "") or "").strip()
            name = str(item.get("name", "") or "").strip()
            if not platform_id or not name:
                skipped += 1
                continue

            listing = db.query(Listing).filter_by(
                platform=platform, platform_id=platform_id
            ).first()

            if listing:
                product = db.query(Product).filter_by(id=listing.product_id).first()
                changed = False
                if product:
                    changed = _apply_external_fields(product, item, platform)
                if listing.status != "success" or listing.error:
                    listing.status = "success"
                    listing.error = ""
                    changed = True
                if changed:
                    updated += 1
                else:
                    skipped += 1
                continue

            product, was_created = _find_or_link_product(db, platform, platform_id, item)
            _apply_external_fields(product, item, platform)
            db.add(Listing(
                product_id=product.id,
                platform=platform,
                platform_id=platform_id,
                status="success",
            ))
            if was_created:
                created += 1
            else:
                linked += 1

        db.commit()

    return {
        "ok": True,
        "total_found": len(items),
        "created": created,
        "linked": linked,
        "updated": updated,
        "skipped": skipped,
    }


def _coupang_item(summary: dict, detail: dict) -> dict:
    detail_items = detail.get("items") or []
    prices = [
        _number(x.get("salePrice"))
        for x in detail_items
        if _number(x.get("salePrice")) > 0
    ]
    images, detail_images = extract_coupang_product_images(detail)
    seller_id = str(summary.get("sellerProductId", "") or detail.get("sellerProductId") or "").strip()
    return {
        "platform_id": seller_id,
        "name": (
            detail.get("displayProductName")
            or detail.get("sellerProductName")
            or summary.get("sellerProductName")
            or ""
        ),
        "price": min(prices) if prices else 0.0,
        "category": str(detail.get("displayCategoryCode") or summary.get("displayCategoryCode") or ""),
        "brand": detail.get("brand") or summary.get("brand") or "",
        "images": images,
        "detail_images": detail_images,
        "image": images[0] if images else "",  # 레거시 호환
        "status": detail.get("statusName") or summary.get("statusName") or "",
    }


def _coupang_catalog_items() -> list[dict]:
    """쿠팡 목록 API + 상세 API로 상품명/가격/대표·상세 이미지를 읽는다."""
    from app.platforms.coupang import get_coupang_uploader

    uploader = get_coupang_uploader()
    summaries = uploader.list_seller_products(max_pages=20, page_size=100)
    results: list[dict] = []

    for summary in summaries:
        seller_id = str(summary.get("sellerProductId", "") or "").strip()
        if not seller_id:
            continue
        detail: dict = {}
        try:
            detail = uploader.get_seller_product(seller_id) or {}
        except Exception as exc:
            logger.warning("쿠팡 상품 상세 조회 실패 [%s]: %s", seller_id, exc)
        results.append(_coupang_item(summary, detail))
    return results


def sync_coupang_catalog(max_pages: int = 20) -> dict:
    """쿠팡 Wing 전체 판매상품을 읽어 신규/수정 내용을 로컬 DB에 반영한다."""
    from app.platforms.coupang import get_coupang_uploader

    try:
        uploader = get_coupang_uploader()
        summaries = uploader.list_seller_products(max_pages=max_pages, page_size=100)
        items: list[dict] = []
        for summary in summaries:
            seller_id = str(summary.get("sellerProductId", "") or "").strip()
            if not seller_id:
                continue
            detail: dict = {}
            try:
                detail = uploader.get_seller_product(seller_id) or {}
            except Exception as exc:
                logger.warning("쿠팡 상품 상세 조회 실패 [%s]: %s", seller_id, exc)
            items.append(_coupang_item(summary, detail))
    except Exception as exc:
        logger.error("쿠팡 카탈로그 동기화 실패: %s", exc)
        return {"ok": False, "error": str(exc)}

    return _sync("coupang", items)


def _smartstore_search_page(uploader, page: int, page_size: int) -> dict:
    """네이버 공식 상품 목록 조회 API POST /v1/products/search 호출."""
    payload = {
        "page": page,
        "size": min(max(int(page_size), 1), 500),
        "orderType": "MOD_DATE",
    }
    response = httpx.post(
        "https://api.commerce.naver.com/external/v1/products/search",
        headers=uploader._headers(),
        json=payload,
        timeout=30,
    )
    if response.status_code != 200:
        raise ValueError(
            f"스마트스토어 상품목록 조회 실패 HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
    return response.json()


def sync_smartstore_catalog(max_pages: int = 20) -> dict:
    """스마트스토어 판매자센터 전체 상품을 공식 상품검색 API로 역동기화한다."""
    from app.platforms.smartstore import get_smartstore_uploader

    try:
        uploader = get_smartstore_uploader()
        items: list[dict] = []

        for page in range(1, max_pages + 1):
            data = _smartstore_search_page(uploader, page=page, page_size=500)
            contents = data.get("contents") or []
            if not isinstance(contents, list) or not contents:
                break

            for row in contents:
                origin_no = str(row.get("originProductNo") or "").strip()
                channels = row.get("channelProducts") or []
                channel = next(
                    (x for x in channels if x.get("channelServiceType") == "STOREFARM"),
                    channels[0] if channels else {},
                )
                if not origin_no:
                    origin_no = str(channel.get("originProductNo") or "").strip()

                image_obj = channel.get("representativeImage") or {}
                image_url = normalize_image_url(image_obj.get("url"), platform="smartstore")
                items.append({
                    "platform_id": origin_no,
                    "name": channel.get("name") or row.get("name") or "",
                    "price": channel.get("salePrice") or row.get("salePrice") or 0,
                    "category": channel.get("wholeCategoryName") or channel.get("categoryId") or "",
                    "brand": channel.get("brandName") or "",
                    "images": [image_url] if image_url else [],
                    "image": image_url,
                    "stock": channel.get("stockQuantity") or 0,
                    "status": channel.get("statusType") or "",
                    "modified_at": channel.get("modifiedDate") or "",
                    "channel_product_no": str(channel.get("channelProductNo") or ""),
                })

            total_pages = int(data.get("totalPages") or 0)
            if data.get("last") is True or (total_pages and page >= total_pages):
                break
            if len(contents) < 500 and not total_pages:
                break

    except Exception as exc:
        logger.error("스마트스토어 카탈로그 동기화 실패: %s", exc)
        return {"ok": False, "error": str(exc)}

    return _sync("smartstore", items)
