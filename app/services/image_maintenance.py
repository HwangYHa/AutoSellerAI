"""Responsive product image maintenance.

Network I/O is deliberately performed outside SQLAlchemy sessions. Each product
update uses a short transaction so the Seller OS can continue reading SQLite
while a long repair job is running in the background.
"""
from __future__ import annotations

import json
from typing import Any

from app.db import Product, get_db
from app.services.product_catalog import SUPPLIER_SOURCES, repair_product_image_urls


def refresh_supplier_images_responsive(limit: int = 300) -> dict[str, Any]:
    from app.suppliers.registry import get_adapter

    with get_db() as db:
        targets = [
            {
                "id": p.id,
                "source": p.source,
                "source_id": p.source_id,
            }
            for p in (
                db.query(Product)
                .filter(Product.source.in_(SUPPLIER_SOURCES))
                .order_by(Product.updated_at.desc())
                .limit(max(1, int(limit)))
                .all()
            )
        ]

    checked = updated = still_missing = 0
    errors: list[str] = []

    for target in targets:
        checked += 1
        source = str(target["source"] or "")
        source_id = str(target["source_id"] or "")
        adapter = get_adapter(source)
        if not adapter or not source_id:
            still_missing += 1
            continue

        try:
            normalized = adapter.get_product(source_id)
        except Exception as exc:
            errors.append(f"#{target['id']} {source}: {exc}")
            continue
        if not normalized:
            errors.append(f"#{target['id']} {source}: 상품 상세 조회 실패")
            continue

        # DB session starts only after the remote call is finished.
        with get_db() as db:
            p = db.query(Product).filter_by(id=int(target["id"])).first()
            if not p:
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
                value = json.dumps(normalized.images, ensure_ascii=False)
                if p.images != value:
                    p.images = value
                    changed = True
            if normalized.detail_images:
                value = json.dumps(normalized.detail_images, ensure_ascii=False)
                if p.detail_images != value:
                    p.detail_images = value
                    changed = True
            if normalized.options:
                value = json.dumps(normalized.options, ensure_ascii=False)
                if p.options != value:
                    p.options = value
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


def repair_all_product_images_responsive(*, include_marketplaces: bool = True) -> dict[str, Any]:
    local = repair_product_image_urls()
    suppliers = refresh_supplier_images_responsive()
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
