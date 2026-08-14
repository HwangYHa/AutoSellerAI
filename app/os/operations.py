"""High-risk Seller OS commands.

No UI should call marketplace/supplier mutation APIs directly.  UI creates an
approval, then this module consumes it through the idempotent operation journal.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.db import get_db
from app.os.approvals import execute_idempotent, request_approval
from app.os.bridge import migrate_legacy_to_os
from app.os.models import (
    OSApprovalRequest,
    OSFulfillment,
    OSListing,
    OSProduct,
    OSSalesOrderItem,
    OSSupplier,
    OSSupplierOffer,
)
from app.os.schema import ensure_os_schema
from app.os.state import FULFILLMENT_STATES, LISTING_STATES, ORDER_ITEM_STATES


def _content(product: OSProduct) -> dict[str, Any]:
    try:
        value = json.loads(product.content_json or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def request_listing_publish(product_id: int, platform: str, *, actor: str = "user") -> dict[str, Any]:
    ensure_os_schema()
    platform = platform.strip().lower()
    if platform not in {"coupang", "smartstore"}:
        return {"ok": False, "error": "지원하지 않는 판매채널입니다."}
    with get_db() as db:
        product = db.query(OSProduct).filter_by(id=int(product_id)).first()
        if not product:
            return {"ok": False, "error": "상품을 찾을 수 없습니다."}
        if product.status not in {"ready", "active"}:
            return {"ok": False, "error": f"판매 준비가 끝난 상품만 등록할 수 있습니다. 현재 상태: {product.status}"}
        content = _content(product)
        legacy_product_id = content.get("legacy_product_id")
        if not legacy_product_id:
            return {"ok": False, "error": "아직 판매채널 업로더와 연결되지 않은 v3 상품입니다."}
        listing = db.query(OSListing).filter_by(product_id=product.id, platform=platform, account_key="default").first()
        if not listing:
            listing = OSListing(
                product_id=product.id,
                platform=platform,
                account_key="default",
                status="draft",
                sale_price_krw=int(content.get("legacy_sell_price", 0) or 0),
                title=product.name,
            )
            db.add(listing)
            db.flush()
        if listing.status == "active":
            return {"ok": True, "already_active": True, "listing_id": listing.id}
        if listing.status not in {"draft", "failed", "pending_approval"}:
            return {"ok": False, "error": f"현재 등록 상태에서는 요청할 수 없습니다: {listing.status}"}
        if listing.status != "pending_approval":
            if listing.status == "failed":
                listing.status = "draft"
            LISTING_STATES.require(listing.status, "pending_approval")
            listing.status = "pending_approval"
        listing_id = listing.id
        db.commit()

    payload = {
        "product_id": int(product_id),
        "listing_id": listing_id,
        "legacy_product_id": int(legacy_product_id),
        "platform": platform,
    }
    approval = request_approval(
        action_type="marketplace.publish",
        entity_type="listing",
        entity_id=listing_id,
        payload=payload,
        summary=f"{platform.upper()}에 '{product.name}' 실제 상품 등록",
        risk_level="high",
        requested_by=actor,
        ttl_minutes=60,
    )
    return {"ok": True, "listing_id": listing_id, **approval}


def execute_listing_publish(approval_id: int, *, actor: str = "user") -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        approval = db.query(OSApprovalRequest).filter_by(id=int(approval_id)).first()
        if not approval:
            return {"ok": False, "error": "승인 요청 없음"}
        try:
            payload = json.loads(approval.payload_json or "{}")
        except Exception:
            return {"ok": False, "error": "승인 payload 손상"}
        if approval.action_type != "marketplace.publish":
            return {"ok": False, "error": "상품등록 승인이 아닙니다."}
        listing = db.query(OSListing).filter_by(id=int(payload.get("listing_id", 0))).first()
        if not listing:
            return {"ok": False, "error": "Listing 없음"}
        if approval.status != "approved":
            return {"ok": False, "error": f"먼저 승인해야 합니다. 현재 상태: {approval.status}"}
        if listing.status == "pending_approval":
            LISTING_STATES.require(listing.status, "publishing")
            listing.status = "publishing"
            db.commit()

    def executor() -> Any:
        from app.pipeline import upload_product
        result = upload_product(int(payload["legacy_product_id"]), [str(payload["platform"])])
        first = result[0] if result else {"status": "failed", "error": "응답 없음"}
        if first.get("status") != "success":
            raise RuntimeError(first.get("error") or "판매채널 등록 실패")
        migrate_legacy_to_os()
        return first

    result = execute_idempotent(
        action_type="marketplace.publish",
        entity_type="listing",
        entity_id=str(payload["listing_id"]),
        payload=payload,
        executor=executor,
        approval_id=int(approval_id),
        require_approval=True,
        actor=actor,
    )
    with get_db() as db:
        listing = db.query(OSListing).filter_by(id=int(payload["listing_id"])).first()
        if listing:
            if result.get("ok"):
                listing.status = "active"
                response = result.get("response") or {}
                listing.external_product_id = str(response.get("platform_id") or listing.external_product_id or "")
                listing.error = ""
                listing.last_synced_at = datetime.utcnow()
            else:
                listing.status = "failed"
                listing.error = str(result.get("error") or "")[:1000]
            db.commit()
    return result


def request_order_fulfillment(order_item_id: int, *, actor: str = "user") -> dict[str, Any]:
    """Create the supplier-order approval package, without sending an order."""
    ensure_os_schema()
    with get_db() as db:
        item = db.query(OSSalesOrderItem).filter_by(id=int(order_item_id)).first()
        if not item:
            return {"ok": False, "error": "주문 품목을 찾을 수 없습니다."}
        if not item.product_id:
            return {"ok": False, "error": "내부 상품과 연결되지 않은 주문입니다."}
        offer = None
        if item.supplier_offer_id:
            offer = db.query(OSSupplierOffer).filter_by(id=item.supplier_offer_id).first()
        if not offer:
            offers = db.query(OSSupplierOffer).filter_by(product_id=item.product_id, status="active").all()
            if len(offers) == 1:
                offer = offers[0]
                item.supplier_offer_id = offer.id
            elif not offers:
                item.status = "exception"
                item.exception_code = "NO_SUPPLIER_OFFER"
                db.commit()
                return {"ok": False, "error": "사용 가능한 공급처 상품이 없습니다."}
            else:
                item.status = "exception"
                item.exception_code = "SUPPLIER_SELECTION_REQUIRED"
                db.commit()
                return {"ok": False, "error": "공급처 후보가 여러 개입니다. 공급처를 먼저 선택하세요."}
        supplier = db.query(OSSupplier).filter_by(id=offer.supplier_id).first()
        fulfillment = db.query(OSFulfillment).filter_by(order_item_id=item.id).first()
        if fulfillment and fulfillment.status in {"ordered", "shipping", "shipped", "completed"}:
            return {"ok": True, "already_ordered": True, "fulfillment_id": fulfillment.id}
        if not fulfillment:
            fulfillment = OSFulfillment(
                order_item_id=item.id,
                supplier_offer_id=offer.id,
                supplier_code=supplier.code if supplier else "",
                status="pending_approval",
                quantity=item.quantity,
                supply_cost_krw=int(offer.supply_price_krw or 0) * int(item.quantity or 1),
                shipping_cost_krw=int(offer.shipping_fee_krw or 0),
            )
            db.add(fulfillment)
            db.flush()
        elif fulfillment.status == "failed":
            FULFILLMENT_STATES.require("failed", "pending_approval")
            fulfillment.status = "pending_approval"
        if item.status == "ready":
            ORDER_ITEM_STATES.require(item.status, "approved")
        fulfillment_id = fulfillment.id
        db.commit()

    payload = {
        "order_item_id": int(order_item_id),
        "fulfillment_id": fulfillment_id,
        "supplier_offer_id": offer.id,
        "supplier_code": supplier.code if supplier else "",
        "supplier_product_id": offer.supplier_product_id,
        "supplier_variant_id": offer.supplier_variant_id,
        "quantity": int(item.quantity or 1),
        "expected_supply_cost_krw": int(offer.supply_price_krw or 0) * int(item.quantity or 1),
        "expected_shipping_cost_krw": int(offer.shipping_fee_krw or 0),
    }
    approval = request_approval(
        action_type="supplier.order",
        entity_type="fulfillment",
        entity_id=fulfillment_id,
        payload=payload,
        summary=(
            f"{supplier.name if supplier else payload['supplier_code']}에 '{item.product_name}' "
            f"{item.quantity}개 실제 발주 · 예상 {payload['expected_supply_cost_krw'] + payload['expected_shipping_cost_krw']:,}원"
        ),
        risk_level="critical",
        requested_by=actor,
        ttl_minutes=30,
    )
    return {"ok": True, "fulfillment_id": fulfillment_id, **approval}


def approve_fulfillment_state(approval_id: int) -> dict[str, Any]:
    """Move an approved supplier order to executable state.

    Actual supplier API execution is intentionally adapter-specific.  A supplier is
    eligible for automatic execution only after its v3 order driver has a verified
    payload mapper, simulation and cancellation behavior.
    """
    ensure_os_schema()
    with get_db() as db:
        approval = db.query(OSApprovalRequest).filter_by(id=int(approval_id)).first()
        if not approval or approval.action_type != "supplier.order":
            return {"ok": False, "error": "공급처 발주 승인 요청이 아닙니다."}
        if approval.status != "approved":
            return {"ok": False, "error": "먼저 승인해야 합니다."}
        payload = json.loads(approval.payload_json or "{}")
        fulfillment = db.query(OSFulfillment).filter_by(id=int(payload.get("fulfillment_id", 0))).first()
        if not fulfillment:
            return {"ok": False, "error": "Fulfillment 없음"}
        if fulfillment.status == "pending_approval":
            FULFILLMENT_STATES.require(fulfillment.status, "approved")
            fulfillment.status = "approved"
        item = db.query(OSSalesOrderItem).filter_by(id=fulfillment.order_item_id).first()
        if item and item.status == "ready":
            ORDER_ITEM_STATES.require(item.status, "approved")
            item.status = "approved"
        db.commit()
        return {
            "ok": True,
            "fulfillment_id": fulfillment.id,
            "status": fulfillment.status,
            "message": "승인 완료. 검증된 공급처 주문 드라이버가 있는 경우에만 자동 실행 대상이 됩니다.",
        }
