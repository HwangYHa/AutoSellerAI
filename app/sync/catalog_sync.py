"""플랫폼에 이미 등록된 상품을 로컬 DB(products/listings)로 가져오는 동기화.

이 앱을 통하지 않고 쿠팡 Wing/스마트스토어 판매자센터에서 직접 등록한 상품은
로컬 DB가 전혀 알지 못한다 — SEO 최적화를 포함한 모든 기능이 이 앱으로 등록한
상품만 대상으로 동작하는 이유. 이 모듈은 각 플랫폼의 "내 상품 목록" API를 읽어
DB에 없는 상품을 채워 넣는다. **플랫폼에는 아무것도 쓰지 않는다 (읽기 전용).**

매칭 규칙:
1. 이미 동일 platform_id로 연결된 Listing이 있으면 스킵
2. `IMPORT-{platform}-{platform_id}` sku로 이전에 가져온 적이 있으면 그 Product에 연결
3. 이름이 정규화 기준으로 동일하고 해당 플랫폼에 아직 연결되지 않은 로컬 Product가 있으면 연결
4. 위 조건에 모두 해당하지 않으면 새 Product(source=f"{platform}_import")를 생성
"""
from __future__ import annotations
import logging

from app.db import Listing, Product, get_db
from app.seo.duplicate_detector import _normalize

logger = logging.getLogger(__name__)


def _find_or_link_product(db, platform: str, platform_id: str, name: str, price: float) -> tuple[Product, bool]:
    """Returns: (product, created) — created=True면 새 Product를 만든 것."""
    sku = f"IMPORT-{platform}-{platform_id}"[:120]

    existing = db.query(Product).filter_by(sku=sku).first()
    if existing:
        return existing, False

    target_key = _normalize(name)[:30]
    for candidate in db.query(Product).all():
        if _normalize(candidate.name)[:30] != target_key:
            continue
        already_linked = db.query(Listing).filter_by(
            product_id=candidate.id, platform=platform, status="success"
        ).first()
        if not already_linked:
            return candidate, False

    product = Product(
        sku=sku, source=f"{platform}_import", source_id=platform_id,
        name=name[:300], supply_price=0.0, sell_price=price or 0.0,
        category="", status="listed",
    )
    db.add(product)
    db.flush()
    return product, True


def _sync(platform: str, items: list[dict], id_key: str, name_key: str, price_key: str) -> dict:
    created, linked, skipped = 0, 0, 0
    with get_db() as db:
        for item in items:
            platform_id = str(item.get(id_key, "") or "")
            name = item.get(name_key, "") or ""
            if not platform_id or not name:
                skipped += 1
                continue

            already = db.query(Listing).filter_by(
                platform=platform, platform_id=platform_id, status="success"
            ).first()
            if already:
                skipped += 1
                continue

            price = float(item.get(price_key, 0) or 0)
            product, was_created = _find_or_link_product(db, platform, platform_id, name, price)
            db.add(Listing(product_id=product.id, platform=platform,
                           platform_id=platform_id, status="success"))
            if was_created:
                created += 1
            else:
                linked += 1
        db.commit()

    return {"ok": True, "total_found": len(items), "created": created,
            "linked": linked, "skipped": skipped}


def sync_coupang_catalog(max_pages: int = 20) -> dict:
    """쿠팡에 등록된 판매상품 목록을 읽어 로컬 DB에 반영한다."""
    from app.platforms.coupang import get_coupang_uploader
    try:
        items = get_coupang_uploader().list_seller_products(max_pages=max_pages)
    except Exception as exc:
        logger.error("쿠팡 카탈로그 동기화 실패: %s", exc)
        return {"ok": False, "error": str(exc)}

    return _sync("coupang", items, "sellerProductId", "sellerProductName", "")


def sync_smartstore_catalog(max_pages: int = 20) -> dict:
    """스마트스토어에 등록된 상품 목록을 읽어 로컬 DB에 반영한다.

    ⚠️ list_origin_products()가 사용하는 엔드포인트는 실제 계정으로 검증되지
    않았다 — 실패하거나 0건이 나오면 app/platforms/smartstore.py의
    list_origin_products() 응답 파싱을 실제 에러/응답을 보고 조정해야 한다.
    """
    from app.platforms.smartstore import get_smartstore_uploader
    try:
        items = get_smartstore_uploader().list_origin_products(max_pages=max_pages)
    except Exception as exc:
        logger.error("스마트스토어 카탈로그 동기화 실패: %s", exc)
        return {"ok": False, "error": str(exc)}

    return _sync("smartstore", items, "originProductNo", "name", "salePrice")
