"""Commerce operations services inspired by multi-market OMS workflows.

Provides local operational controls without bypassing marketplace/supplier safety gates:
- reusable marketplace-item -> canonical product matching rules
- shipment hold/release and delay visibility
- claim ingestion/read model
- supplier order export rows for manual/partner handoff
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from typing import Any

from app.db import get_db
from app.os.commerce_ops_models import OSOrderClaim, OSOrderOpsState, OSProductMatchRule
from app.os.models import OSFulfillment, OSProduct, OSProductVariant, OSSalesOrder, OSSalesOrderItem, OSSupplierOffer
from app.os.schema import ensure_os_schema


def save_match_rule(
    *,
    platform: str,
    external_item_id: str,
    product_id: int,
    variant_id: int | None = None,
    supplier_offer_id: int | None = None,
    external_product_id: str = "",
    note: str = "",
) -> dict[str, Any]:
    ensure_os_schema()
    platform = str(platform or "").strip().lower()
    external_item_id = str(external_item_id or "").strip()
    if not platform or not external_item_id:
        return {"ok": False, "error": "판매채널과 외부 품목 ID가 필요합니다."}
    with get_db() as db:
        product = db.query(OSProduct).filter_by(id=int(product_id)).first()
        if not product:
            return {"ok": False, "error": "연결할 Product가 없습니다."}
        if variant_id and not db.query(OSProductVariant).filter_by(id=int(variant_id), product_id=product.id).first():
            return {"ok": False, "error": "선택한 Variant가 Product와 일치하지 않습니다."}
        if supplier_offer_id and not db.query(OSSupplierOffer).filter_by(id=int(supplier_offer_id), product_id=product.id).first():
            return {"ok": False, "error": "선택한 공급처 Offer가 Product와 일치하지 않습니다."}
        row = db.query(OSProductMatchRule).filter_by(platform=platform, external_item_id=external_item_id).first()
        if not row:
            row = OSProductMatchRule(platform=platform, external_item_id=external_item_id, product_id=product.id)
            db.add(row)
        row.external_product_id = str(external_product_id or "")
        row.product_id = product.id
        row.variant_id = int(variant_id) if variant_id else None
        row.supplier_offer_id = int(supplier_offer_id) if supplier_offer_id else None
        row.enabled = True
        row.note = str(note or "")[:400]
        db.commit()
        return {"ok": True, "rule_id": row.id}


def apply_match_rules(limit: int = 500) -> dict[str, Any]:
    """Apply deterministic rules to currently unlinked order items.

    Exact marketplace external_item_id match only. This deliberately avoids fuzzy
    matching that could route a real customer order to the wrong supplier product.
    """
    ensure_os_schema()
    matched = 0
    skipped = 0
    with get_db() as db:
        items = (
            db.query(OSSalesOrderItem)
            .join(OSSalesOrder, OSSalesOrder.id == OSSalesOrderItem.order_id)
            .filter(OSSalesOrderItem.product_id.is_(None))
            .order_by(OSSalesOrderItem.id.asc())
            .limit(max(1, int(limit)))
            .all()
        )
        for item in items:
            order = db.query(OSSalesOrder).filter_by(id=item.order_id).first()
            rule = (
                db.query(OSProductMatchRule)
                .filter_by(platform=str(order.platform or "").lower(), external_item_id=str(item.external_item_id or ""), enabled=True)
                .order_by(OSProductMatchRule.priority.asc(), OSProductMatchRule.id.asc())
                .first()
            )
            if not rule:
                skipped += 1
                continue
            item.product_id = rule.product_id
            item.variant_id = rule.variant_id
            item.supplier_offer_id = rule.supplier_offer_id
            if item.status == "exception" and item.exception_code in {"UNLINKED_PRODUCT", "PRODUCT_MATCH_REQUIRED"}:
                item.status = "ready"
                item.exception_code = ""
            matched += 1
        db.commit()
    return {"ok": True, "matched": matched, "skipped": skipped}


def set_shipment_hold(order_item_ids: list[int], *, hold: bool, reason: str = "") -> dict[str, Any]:
    ensure_os_schema()
    updated = 0
    with get_db() as db:
        for raw_id in order_item_ids:
            item_id = int(raw_id)
            item = db.query(OSSalesOrderItem).filter_by(id=item_id).first()
            if not item:
                continue
            row = db.query(OSOrderOpsState).filter_by(order_item_id=item_id).first()
            if not row:
                row = OSOrderOpsState(order_item_id=item_id)
                db.add(row)
            row.shipment_hold = bool(hold)
            row.hold_reason = str(reason or "")[:500] if hold else ""
            updated += 1
        db.commit()
    return {"ok": True, "updated": updated, "hold": bool(hold)}


def set_shipment_deadline(order_item_ids: list[int], *, hours_from_now: int = 24) -> dict[str, Any]:
    ensure_os_schema()
    deadline = datetime.utcnow() + timedelta(hours=max(1, int(hours_from_now)))
    updated = 0
    with get_db() as db:
        for raw_id in order_item_ids:
            item_id = int(raw_id)
            if not db.query(OSSalesOrderItem).filter_by(id=item_id).first():
                continue
            row = db.query(OSOrderOpsState).filter_by(order_item_id=item_id).first()
            if not row:
                row = OSOrderOpsState(order_item_id=item_id)
                db.add(row)
            row.shipment_deadline = deadline
            row.delay_notified = False
            updated += 1
        db.commit()
    return {"ok": True, "updated": updated, "shipment_deadline": deadline.isoformat()}


def ingest_claims(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize claims collected by marketplace-specific adapters.

    This function is intentionally adapter-agnostic. Platform collectors can feed
    cancel/return/exchange records here without UI code depending on raw API shapes.
    """
    ensure_os_schema()
    inserted = 0
    updated = 0
    blocked = 0
    with get_db() as db:
        for c in claims:
            platform = str(c.get("platform") or "").strip().lower()
            external_claim_id = str(c.get("external_claim_id") or "").strip()
            if not platform or not external_claim_id:
                continue
            row = db.query(OSOrderClaim).filter_by(platform=platform, external_claim_id=external_claim_id).first()
            if not row:
                row = OSOrderClaim(platform=platform, external_claim_id=external_claim_id, claim_type=str(c.get("claim_type") or "cancel"))
                db.add(row)
                inserted += 1
            else:
                updated += 1
            row.external_order_id = str(c.get("external_order_id") or "")
            row.external_item_id = str(c.get("external_item_id") or "")
            row.claim_type = str(c.get("claim_type") or row.claim_type or "cancel")
            row.status = str(c.get("status") or "requested")
            row.reason = str(c.get("reason") or "")[:500]
            row.raw_json = json.dumps(c.get("raw") or c, ensure_ascii=False, default=str)
            if row.status in {"requested", "approved", "processing"} and row.external_item_id:
                order = db.query(OSSalesOrder).filter_by(platform=platform, external_order_id=row.external_order_id).first()
                item = db.query(OSSalesOrderItem).filter_by(order_id=order.id, external_item_id=row.external_item_id).first() if order else None
                if item:
                    state = db.query(OSOrderOpsState).filter_by(order_item_id=item.id).first()
                    if not state:
                        state = OSOrderOpsState(order_item_id=item.id)
                        db.add(state)
                    state.claim_blocked = True
                    state.shipment_hold = True
                    state.hold_reason = f"{row.claim_type.upper()} CLAIM: {row.reason}"[:500]
                    blocked += 1
        db.commit()
    return {"ok": True, "inserted": inserted, "updated": updated, "blocked_order_items": blocked}


def get_commerce_ops_dashboard(limit: int = 500) -> dict[str, Any]:
    ensure_os_schema()
    now = datetime.utcnow()
    with get_db() as db:
        items = (
            db.query(OSSalesOrderItem)
            .join(OSSalesOrder, OSSalesOrder.id == OSSalesOrderItem.order_id)
            .order_by(OSSalesOrder.ordered_at.desc(), OSSalesOrderItem.id.desc())
            .limit(max(1, int(limit)))
            .all()
        )
        rows = []
        metrics = {"total": 0, "unmatched": 0, "held": 0, "delayed": 0, "claims": 0, "invoice_pending": 0, "exceptions": 0}
        active_claim_keys = {
            (x.platform, x.external_order_id, x.external_item_id)
            for x in db.query(OSOrderClaim).filter(OSOrderClaim.status.in_(["requested", "approved", "processing"])).all()
        }
        for item in items:
            order = db.query(OSSalesOrder).filter_by(id=item.order_id).first()
            f = db.query(OSFulfillment).filter_by(order_item_id=item.id).first()
            ops = db.query(OSOrderOpsState).filter_by(order_item_id=item.id).first()
            claim = bool(order and (order.platform, order.external_order_id, item.external_item_id) in active_claim_keys)
            delayed = bool(ops and ops.shipment_deadline and ops.shipment_deadline < now and item.status not in {"shipped", "completed", "cancelled"})
            invoice_pending = bool(f and f.status in {"ordered", "shipping"} and not f.invoice_registered)
            metrics["total"] += 1
            metrics["unmatched"] += int(item.product_id is None)
            metrics["held"] += int(bool(ops and ops.shipment_hold))
            metrics["delayed"] += int(delayed)
            metrics["claims"] += int(claim)
            metrics["invoice_pending"] += int(invoice_pending)
            metrics["exceptions"] += int(bool(item.exception_code))
            rows.append({
                "order_item_id": item.id,
                "platform": order.platform if order else "",
                "order_no": order.external_order_id if order else "",
                "external_item_id": item.external_item_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "sale_amount_krw": int(item.unit_sale_price_krw or 0) * int(item.quantity or 0),
                "product_id": item.product_id,
                "variant_id": item.variant_id,
                "supplier_offer_id": item.supplier_offer_id,
                "item_status": item.status,
                "exception_code": item.exception_code,
                "shipment_hold": bool(ops and ops.shipment_hold),
                "hold_reason": ops.hold_reason if ops else "",
                "shipment_deadline": ops.shipment_deadline if ops else None,
                "delayed": delayed,
                "claim_active": claim,
                "supplier_code": f.supplier_code if f else "",
                "supplier_order_id": f.supplier_order_id if f else "",
                "fulfillment_status": f.status if f else "",
                "delivery_company": f.delivery_company if f else "",
                "tracking_number": f.tracking_number if f else "",
                "invoice_registered": bool(f and f.invoice_registered),
            })
        claims = db.query(OSOrderClaim).order_by(OSOrderClaim.updated_at.desc()).limit(200).all()
        rules = db.query(OSProductMatchRule).order_by(OSProductMatchRule.priority.asc(), OSProductMatchRule.id.desc()).limit(500).all()
        return {
            "metrics": metrics,
            "rows": rows,
            "claims": [{"id": x.id, "platform": x.platform, "claim_id": x.external_claim_id, "order_no": x.external_order_id, "item_id": x.external_item_id, "type": x.claim_type, "status": x.status, "reason": x.reason, "updated_at": x.updated_at} for x in claims],
            "rules": [{"id": x.id, "platform": x.platform, "external_product_id": x.external_product_id, "external_item_id": x.external_item_id, "product_id": x.product_id, "variant_id": x.variant_id, "supplier_offer_id": x.supplier_offer_id, "enabled": x.enabled, "priority": x.priority, "note": x.note} for x in rules],
        }


def build_supplier_order_csv(order_item_ids: list[int]) -> str:
    """Create a supplier handoff CSV for suppliers without a verified order API."""
    ensure_os_schema()
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["판매채널", "주문번호", "외부품목ID", "상품명", "수량", "수취인", "연락처", "주소", "배송메모", "공급처", "공급상품ID", "공급옵션ID", "예상공급가", "예상배송비"])
    writer.writeheader()
    with get_db() as db:
        for raw_id in order_item_ids:
            item = db.query(OSSalesOrderItem).filter_by(id=int(raw_id)).first()
            if not item:
                continue
            order = db.query(OSSalesOrder).filter_by(id=item.order_id).first()
            offer = db.query(OSSupplierOffer).filter_by(id=item.supplier_offer_id).first() if item.supplier_offer_id else None
            writer.writerow({
                "판매채널": order.platform if order else "",
                "주문번호": order.external_order_id if order else "",
                "외부품목ID": item.external_item_id,
                "상품명": item.product_name,
                "수량": item.quantity,
                "수취인": order.receiver_name if order else "",
                "연락처": order.receiver_phone if order else "",
                "주소": order.shipping_address if order else "",
                "배송메모": order.shipping_message if order else "",
                "공급처": "",
                "공급상품ID": offer.supplier_product_id if offer else "",
                "공급옵션ID": offer.supplier_variant_id if offer else "",
                "예상공급가": int(offer.supply_price_krw or 0) * int(item.quantity or 1) if offer else 0,
                "예상배송비": int(offer.shipping_fee_krw or 0) if offer else 0,
            })
    return out.getvalue()
