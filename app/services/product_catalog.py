"""상품관리 화면이 사용하는 단일 카탈로그 서비스.

UI가 Product/Listing 테이블 구조나 공급처별 예외를 직접 알지 않도록
검색·필터·이미지 정규화·상태 계산·이미지 재수집을 이 계층에서 처리한다.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_

from app.db import Listing, Product, get_db
from app.media.marketplace_images import first_display_image, normalize_image_list


SOURCE_LABELS = {
    "domeggook": "도매꾹",
    "domemai": "도매매",
    "onchannel": "온채널",
    "ownerclan": "오너클랜",
    "coupang_import": "쿠팡 직접등록",
    "smartstore_import": "스마트스토어 직접등록",
}
STATUS_LABELS = {"draft": "준비중", "ready": "판매 준비", "listed": "판매중"}
SUPPLIER_SOURCES = {"domeggook", "domemai", "onchannel", "ownerclan"}


def _json_list(raw: str | None) -> list[Any]:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _margin_pct(sell_price: float, supply_price: float) -> float | None:
    if sell_price <= 0 or supply_price <= 0:
        return None
    return round((sell_price - supply_price) / sell_price * 100, 1)


def _source_platform(source: str) -> str:
    if source == "coupang_import":
        return "coupang"
    if source == "smartstore_import":
        return "smartstore"
    return ""


def _listing_map(db, product_ids: list[int]) -> dict[int, list[dict]]:
    result: dict[int, list[dict]] = {pid: [] for pid in product_ids}
    if not product_ids:
        return result
    rows = db.query(Listing).filter(Listing.product_id.in_(product_ids)).all()
    for row in rows:
        result.setdefault(row.product_id, []).append({
            "platform": row.platform,
            "platform_id": row.platform_id,
            "status": row.status,
            "error": row.error or "",
        })
    return result


def _product_row(p: Product, listings: list[dict]) -> dict[str, Any]:
    images_raw = _json_list(p.images)
    detail_raw = _json_list(p.detail_images)
    platform = _source_platform(p.source)
    images = normalize_image_list(images_raw, platform=platform)
    details = normalize_image_list(detail_raw, platform=platform)
    image_url = first_display_image(images, source=p.source)
    successful_channels = [x["platform"] for x in listings if x["status"] == "success"]
    failed_channels = [x for x in listings if x["status"] == "failed"]

    issues: list[str] = []
    if not image_url:
        issues.append("대표 이미지 없음")
    if float(p.sell_price or 0) <= 0:
        issues.append("판매가 미설정")
    if failed_channels:
        issues.append("채널 등록 실패")
    if p.source in SUPPLIER_SOURCES and float(p.supply_price or 0) <= 0:
        issues.append("공급가 확인 필요")

    return {
        "id": p.id,
        "sku": p.sku,
        "source": p.source,
        "source_label": SOURCE_LABELS.get(p.source, p.source or "기타"),
        "source_id": p.source_id,
        "source_url": p.source_url or "",
        "name": p.name,
        "supply_price": float(p.supply_price or 0),
        "sell_price": float(p.sell_price or 0),
        "margin_pct": _margin_pct(float(p.sell_price or 0), float(p.supply_price or 0)),
        "status": p.status,
        "status_label": STATUS_LABELS.get(p.status, p.status),
        "category": p.category or "",
        "brand": p.brand or "",
        "origin": p.origin or "",
        "images": images,
        "detail_images": details,
        "image_url": image_url,
        "image_count": len(images),
        "detail_image_count": len(details),
        "listings": listings,
        "channels": successful_channels,
        "issues": issues,
        "needs_action": bool(issues),
        "updated_at": p.updated_at.strftime("%Y-%m-%d %H:%M") if p.updated_at else "",
    }


def get_catalog(
    *,
    search: str = "",
    status: str = "",
    source: str = "",
    channel: str = "",
    page: int = 1,
    page_size: int = 24,
    action_only: bool = False,
) -> dict[str, Any]:
    page = max(1, int(page))
    page_size = max(6, min(100, int(page_size)))

    with get_db() as db:
        q = db.query(Product)
        if search.strip():
            term = f"%{search.strip()}%"
            q = q.filter(or_(Product.name.ilike(term), Product.sku.ilike(term), Product.source_id.ilike(term)))
        if status:
            q = q.filter(Product.status == status)
        if source:
            q = q.filter(Product.source == source)
        if channel:
            linked_ids = db.query(Listing.product_id).filter(
                Listing.platform == channel,
                Listing.status == "success",
            ).subquery()
            q = q.filter(Product.id.in_(linked_ids))

        total_before_action = q.count()
        rows = q.order_by(Product.updated_at.desc(), Product.id.desc()).all()
        listing_map = _listing_map(db, [p.id for p in rows])
        normalized = [_product_row(p, listing_map.get(p.id, [])) for p in rows]
        if action_only:
            normalized = [row for row in normalized if row["needs_action"]]

        total = len(normalized)
        start = (page - 1) * page_size
        items = normalized[start:start + page_size]

        all_products = db.query(Product).all()
        all_listing_map = _listing_map(db, [p.id for p in all_products])
        all_rows = [_product_row(p, all_listing_map.get(p.id, [])) for p in all_products]

    metrics = {
        "total": len(all_rows),
        "listed": sum(1 for x in all_rows if x["status"] == "listed"),
        "ready": sum(1 for x in all_rows if x["status"] == "ready"),
        "needs_action": sum(1 for x in all_rows if x["needs_action"]),
        "no_image": sum(1 for x in all_rows if not x["image_url"]),
    }
    sources = sorted({x["source"] for x in all_rows if x["source"]})
    return {
        "items": items,
        "total": total,
        "filtered_total": total_before_action,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "metrics": metrics,
        "sources": sources,
    }


def get_product_snapshot(product_id: int) -> dict[str, Any] | None:
    with get_db() as db:
        p = db.query(Product).filter_by(id=int(product_id)).first()
        if not p:
            return None
        listings = _listing_map(db, [p.id]).get(p.id, [])
        row = _product_row(p, listings)
        row["detail_html"] = p.detail_html or ""
        row["options"] = _json_list(p.options)
        row["material"] = p.material or ""
        return row


def repair_product_image_urls() -> dict[str, int]:
    """기존 DB에 저장된 상대/깨진 마켓 이미지 경로를 안전하게 정리한다."""
    checked = changed = removed = 0
    with get_db() as db:
        products = db.query(Product).all()
        for p in products:
            checked += 1
            platform = _source_platform(p.source)
            old_images = _json_list(p.images)
            old_details = _json_list(p.detail_images)
            new_images = normalize_image_list(old_images, platform=platform)
            new_details = normalize_image_list(old_details, platform=platform)
            if new_images != old_images:
                removed += max(0, len(old_images) - len(new_images))
                p.images = json.dumps(new_images, ensure_ascii=False)
                changed += 1
            if new_details != old_details:
                removed += max(0, len(old_details) - len(new_details))
                p.detail_images = json.dumps(new_details, ensure_ascii=False)
                changed += 1
        db.commit()
    return {"checked": checked, "changed": changed, "removed": removed}


def refresh_supplier_product_images(
    product_ids: list[int] | None = None,
    *,
    limit: int = 300,
) -> dict[str, Any]:
    """공급처 원본을 다시 조회해 대표/상세 이미지를 DB에 갱신한다.

    adapter.get_product()는 registry의 이미지 보완 프록시를 통과하므로 API 이미지뿐 아니라
    원본 HTML의 img/lazy/srcset/background/JSON 이미지까지 수집한다. 온채널은 로그인
    세션을 재사용한다.
    """
    from app.suppliers.registry import get_adapter

    ids = {int(x) for x in (product_ids or [])}
    checked = updated = still_missing = 0
    errors: list[str] = []

    with get_db() as db:
        q = db.query(Product).filter(Product.source.in_(SUPPLIER_SOURCES))
        if ids:
            q = q.filter(Product.id.in_(ids))
        products = q.order_by(Product.updated_at.desc()).limit(max(1, int(limit))).all()

        for p in products:
            checked += 1
            adapter = get_adapter(p.source)
            if not adapter or not p.source_id:
                still_missing += 1
                continue
            try:
                normalized = adapter.get_product(str(p.source_id))
            except Exception as exc:
                errors.append(f"#{p.id} {p.source}: {exc}")
                continue
            if not normalized:
                errors.append(f"#{p.id} {p.source}: 상품 상세 조회 실패")
                continue

            changed = False
            if normalized.raw_url and p.source_url != normalized.raw_url:
                p.source_url = normalized.raw_url
                changed = True
            if normalized.supply_price > 0 and float(p.supply_price or 0) != float(normalized.supply_price):
                p.supply_price = normalized.supply_price
                changed = True
            for attr in ("category", "brand", "origin", "material"):
                value = str(getattr(normalized, attr, "") or "").strip()
                if value and getattr(p, attr) != value:
                    setattr(p, attr, value)
                    changed = True

            if normalized.images:
                images_json = json.dumps(normalized.images, ensure_ascii=False)
                if p.images != images_json:
                    p.images = images_json
                    changed = True
            if normalized.detail_images:
                details_json = json.dumps(normalized.detail_images, ensure_ascii=False)
                if p.detail_images != details_json:
                    p.detail_images = details_json
                    changed = True
            if normalized.options:
                options_json = json.dumps(normalized.options, ensure_ascii=False)
                if p.options != options_json:
                    p.options = options_json
                    changed = True

            if changed:
                updated += 1
            if not normalized.images:
                still_missing += 1

        db.commit()

    return {
        "checked": checked,
        "updated": updated,
        "still_missing": still_missing,
        "errors": errors[:30],
    }


def repair_all_product_images(*, include_marketplaces: bool = True) -> dict[str, Any]:
    """Seller OS의 '이미지 복구' 단일 진입점.

    1) DB의 명백히 잘못된 상대 마켓 URL 정리
    2) 모든 공급처 원본 재조회
    3) 필요 시 쿠팡/스마트스토어 기존 판매상품 재동기화
    """
    local = repair_product_image_urls()
    suppliers = refresh_supplier_product_images()
    marketplaces: dict[str, Any] = {}

    if include_marketplaces:
        try:
            from app.sync.catalog_sync import sync_coupang_catalog
            marketplaces["coupang"] = sync_coupang_catalog()
        except Exception as exc:
            marketplaces["coupang"] = {"ok": False, "error": str(exc)}
        try:
            from app.sync.catalog_sync import sync_smartstore_catalog
            marketplaces["smartstore"] = sync_smartstore_catalog()
        except Exception as exc:
            marketplaces["smartstore"] = {"ok": False, "error": str(exc)}

    return {"local": local, "suppliers": suppliers, "marketplaces": marketplaces}


def set_products_status(product_ids: list[int], status: str) -> int:
    if status not in {"draft", "ready", "listed"}:
        raise ValueError("허용되지 않은 상품 상태")
    ids = [int(x) for x in product_ids]
    if not ids:
        return 0
    with get_db() as db:
        rows = db.query(Product).filter(Product.id.in_(ids)).all()
        for row in rows:
            row.status = status
        db.commit()
        return len(rows)


def delete_products(product_ids: list[int]) -> int:
    ids = [int(x) for x in product_ids]
    if not ids:
        return 0
    with get_db() as db:
        db.query(Listing).filter(Listing.product_id.in_(ids)).delete(synchronize_session=False)
        count = db.query(Product).filter(Product.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        return int(count or 0)
