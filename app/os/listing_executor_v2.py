"""Template-aware approved marketplace listing executor.

The legacy Product table remains the physical uploader source for compatibility, but
all reusable channel-template values are merged immediately before the external API
call. Explicit product values always win.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.db import Listing as LegacyListing, Product as LegacyProduct, get_db
from app.os.approvals import execute_idempotent
from app.os.bridge import migrate_legacy_to_os
from app.os.commerce_automation import apply_channel_template
from app.os.models import OSApprovalRequest, OSListing
from app.os.schema import ensure_os_schema


def _legacy_payload(p: LegacyProduct) -> dict[str, Any]:
    def loads(value: str, default):
        try:
            parsed = json.loads(value or "")
            return parsed if parsed is not None else default
        except Exception:
            return default
    return {
        "sku": p.sku,
        "name": p.name,
        "sell_price": float(p.sell_price or 0),
        "supply_price": float(p.supply_price or 0),
        "stock": 999,
        "category": p.category,
        "brand": p.brand,
        "origin": p.origin,
        "material": p.material,
        "images": loads(p.images, []),
        "detail_images": loads(p.detail_images, []),
        "options": loads(p.options, []),
        "detail_html": p.detail_html or "",
        "shipping_fee": 3000,
        "return_fee": 3000,
    }


def execute_listing_publish_v2(approval_id: int, *, actor: str = "worker") -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        approval = db.query(OSApprovalRequest).filter_by(id=int(approval_id)).first()
        if not approval or approval.action_type != "marketplace.publish":
            return {"ok": False, "error": "상품등록 승인이 아닙니다."}
        if approval.status not in {"approved", "consumed"}:
            return {"ok": False, "error": f"먼저 승인해야 합니다. 현재 상태: {approval.status}"}
        try:
            payload = json.loads(approval.payload_json or "{}")
        except Exception:
            return {"ok": False, "error": "승인 payload 손상"}
        platform = str(payload.get("platform") or "").lower()
        listing = db.query(OSListing).filter_by(id=int(payload.get("listing_id") or 0)).first()
        legacy = db.query(LegacyProduct).filter_by(id=int(payload.get("legacy_product_id") or 0)).first()
        if not listing or not legacy:
            return {"ok": False, "error": "Listing 또는 원본 Product가 없습니다."}
        listing.status = "publishing"
        db.commit()
        legacy_product_id = int(legacy.id)
        base_product = _legacy_payload(legacy)

    prepared = apply_channel_template(base_product, platform)

    def executor() -> dict[str, Any]:
        if platform == "coupang":
            from app.platforms.coupang import reset_coupang_uploader, get_coupang_uploader
            reset_coupang_uploader()
            raw = get_coupang_uploader().create_product(prepared)
            external_id = str((raw.get("data") or {}).get("sellerProductId") or "")
        elif platform == "smartstore":
            from app.platforms.smartstore import reset_smartstore_uploader, get_smartstore_uploader
            reset_smartstore_uploader()
            raw = get_smartstore_uploader().create_product(prepared)
            external_id = str(raw.get("originProductNo") or raw.get("channelProductNo") or "")
        else:
            raise RuntimeError(f"지원하지 않는 판매채널: {platform}")
        if not external_id:
            raise RuntimeError(f"{platform} 상품등록 응답에서 외부 상품번호를 찾지 못했습니다: {str(raw)[:500]}")
        with get_db() as db:
            row = LegacyListing(product_id=legacy_product_id, platform=platform, platform_id=external_id, status="success")
            db.add(row)
            product = db.query(LegacyProduct).filter_by(id=legacy_product_id).first()
            if product: product.status = "listed"
            db.commit()
        return {"platform": platform, "status": "success", "platform_id": external_id, "template_id": prepared.get("channel_template_id"), "template_name": prepared.get("channel_template_name", "")}

    result = execute_idempotent(
        action_type="marketplace.publish",
        entity_type="listing",
        entity_id=str(payload["listing_id"]),
        payload={**payload, "template_id": prepared.get("channel_template_id")},
        executor=executor,
        approval_id=int(approval_id),
        require_approval=True,
        actor=actor,
    )
    with get_db() as db:
        listing = db.query(OSListing).filter_by(id=int(payload["listing_id"])).first()
        if listing:
            if result.get("ok"):
                response = result.get("response") or {}
                listing.status = "active"
                listing.external_product_id = str(response.get("platform_id") or listing.external_product_id or "")
                listing.error = ""
                listing.last_synced_at = datetime.utcnow()
            else:
                listing.status = "failed"
                listing.error = str(result.get("error") or "")[:1000]
            db.commit()
    if result.get("ok"):
        migrate_legacy_to_os()
    return result
