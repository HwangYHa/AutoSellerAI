"""Seller OS sourcing application service.

During the strangler migration, marketplace publishing still depends on the legacy
Product row.  This service owns that compatibility write and immediately reconciles
the result into the canonical Seller OS v3 tables so the user never has to hunt for
an imported product or manually run a data bridge.
"""
from __future__ import annotations

from typing import Any

from app.db import get_db
from app.os.bridge import migrate_legacy_to_os
from app.os.models import OSProduct
from app.os.schema import ensure_os_schema


def import_supplier_product(
    source: str,
    source_id: str,
    sell_price: float,
    ai_enhance: bool = True,
) -> dict[str, Any]:
    """Import one supplier product and make it visible in Seller OS immediately.

    The legacy Product write is transitional infrastructure required by the current
    Coupang/SmartStore upload adapters.  New callers must use this application
    service rather than calling ``app.pipeline.import_product`` from the UI.
    """
    ensure_os_schema()

    from app.pipeline import import_product as legacy_import_product

    result = legacy_import_product(source, source_id, sell_price, ai_enhance)
    if result.get("status") not in {"imported", "updated"}:
        return result

    bridge = migrate_legacy_to_os()
    if not bridge.get("ok"):
        return {
            **result,
            "status": "error",
            "error": "기존 상품 저장 후 Seller OS 반영에 실패했습니다.",
            "bridge": bridge,
        }

    sku = str(result.get("sku") or "")
    with get_db() as db:
        os_product = db.query(OSProduct).filter_by(sku=sku).first() if sku else None
        if not os_product:
            return {
                **result,
                "status": "error",
                "error": "상품은 저장됐지만 Seller OS 상품을 찾지 못했습니다. 데이터 관계 복구가 필요합니다.",
                "bridge": bridge,
            }
        os_product_id = int(os_product.id)
        os_status = str(os_product.status or "")

    return {
        **result,
        "os_product_id": os_product_id,
        "os_status": os_status,
        "bridge": bridge,
    }
