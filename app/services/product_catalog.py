"""상품관리 화면이 사용하는 단일 카탈로그 서비스.

UI가 Product/Listing 테이블 구조나 공급처별 예외를 직접 알지 않도록
검색·필터·이미지 정규화·상태 계산을 이 계층에서 한 번에 처리한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
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
    if p.source in {"domeggook", "domemai", "onchannel", "ownerclan"} and float(p.supply_price or 0) <= 0:
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
    """상품관리 목록과 필터/요약 데이터를 한 번에 반환한다."""
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
    """기존 DB에 저장된 상대/깨진 마켓 이미지 경로를 안전하게 정리한다.

    절대 URL로 복구할 수 있는 쿠팡 cdnPath는 변환하고, 복구 불가능한 파일명만
    저장된 값은 제거한다. 다음 쿠팡/스마트스토어 동기화가 실행되면 최신 이미지로
    다시 채워진다.
    """
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
