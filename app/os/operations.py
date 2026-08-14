"""High-risk Seller OS commands.

No UI calls marketplace/supplier mutation APIs directly. The application creates an
approval package first; approved external mutations are executed by the dangerous
RQ worker through the idempotency journal.
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
from app.os.quality_models import OSOfferVerification
from app.os.schema import ensure_os_schema
from app.os.state import FULFILLMENT_STATES, LISTING_STATES, ORDER_ITEM_STATES


def _content(product: OSProduct) -> dict[str, Any]:
    try:
        value = json.loads(product.content_json or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _marketplace_preflight(platform: str) -> str:
    """Reject dangerous publish requests before approval if credentials are invalid."""
    from app.os.connections import get_connections

    row = next((x for x in get_connections() if x.get("code") == platform), None)
    if row and row.get("configured"):
        return ""
    if platform == "smartstore":
        return (
            "네이버 스마트스토어 Commerce API 설정이 올바르지 않습니다. "
            "NAVER_CLIENT_SECRET에는 검색 API Secret이 아니라 29자리 bcrypt 형식의 Commerce API Secret($2a$/$2b$/$2y$...)을 입력하고, "
            "검색 API Secret은 NAVER_SEARCH_CLIENT_SECRET에 분리하세요."
        )
    if platform == "coupang":
        return "쿠팡 Access Key / Secret Key / Vendor ID 설정을 먼저 확인하세요."
    return "판매채널 연결 설정을 먼저 확인하세요."


def request_listing_publish(product_id: int, platform: str, *, actor: str = "user") -> dict[str, Any]:
    ensure_os_schema()
    platform = platform.strip().lower()
    if platform not in {"coupang", "smartstore"}:
        return {"ok": False, "error": "지원하지 않는 판매채널입니다."}
    connection_error = _marketplace_preflight(platform)
    if connection_error:
        return {"ok": False, "error": connection_error, "code": "MARKETPLACE_CONNECTION_NOT_READY"}

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

        product_name = product.name
        listing = db.query(OSListing).filter_by(
            product_id=product.id, platform=platform, account_key="default"
        ).first()
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

        listing_id = int(listing.id)
        payload = {
            "product_id": int(product_id),
            "listing_id": listing_id,
            "legacy_product_id": int(legacy_product_id),
            "platform": platform,
        }
        db.commit()

    approval = request_approval(
        action_type="marketplace.publish",
        entity_type="listing",
        entity_id=listing_id,
        payload=payload,
        summary=f"{platform.upper()}에 '{product_name}' 실제 상품 등록",
        risk_level="high",
        requested_by=actor,
        ttl_minutes=60,
    )
    return {"ok": True, "listing_id": listing_id, **approval}


def execute_listing_publish(approval_id: int, *, actor: str = "worker") -> dict[str, Any]:
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
        platform = str(payload.get("platform") or "")
        connection_error = _marketplace_preflight(platform)
        if connection_error:
            return {"ok": False, "error": connection_error, "code": "MARKETPLACE_CONNECTION_NOT_READY"}
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
                response = result.get("response") or {}
                listing.status = "active"
                external = response.get("platform_id")
                if external:
                    listing.external_product_id = str(external)
                listing.error = ""
                listing.last_synced_at = datetime.utcnow()
            else:
                listing.status = "failed"
                listing.error = str(result.get("error") or "")[:1000]
            db.commit()
    return result


def _select_supplier_offer(db, item: OSSalesOrderItem) -> tuple[OSSupplierOffer | None, str]:
    if item.supplier_offer_id:
        existing = db.query(OSSupplierOffer).filter_by(id=item.supplier_offer_id, status="active").first()
        if existing:
            if item.variant_id and existing.variant_id not in {None, item.variant_id}:
                return None, "SUPPLIER_VARIANT_MISMATCH"
            return existing, ""
    base = db.query(OSSupplierOffer).filter_by(product_id=item.product_id, status="active")
    if item.variant_id:
        exact = base.filter(OSSupplierOffer.variant_id == item.variant_id).all()
        if len(exact) == 1: return exact[0], ""
        if len(exact) > 1: return None, "SUPPLIER_SELECTION_REQUIRED"
        fallback = base.filter(OSSupplierOffer.variant_id.is_(None)).all()
        if len(fallback) == 1: return fallback[0], ""
        if len(fallback) > 1: return None, "SUPPLIER_SELECTION_REQUIRED"
        return None, "NO_VARIANT_OFFER"
    offers = base.all()
    if len(offers) == 1: return offers[0], ""
    if not offers: return None, "NO_SUPPLIER_OFFER"
    return None, "SUPPLIER_SELECTION_REQUIRED"


def _validate_offer_for_order(db, item: OSSalesOrderItem, offer: OSSupplierOffer) -> tuple[str, OSOfferVerification | None]:
    verification = db.query(OSOfferVerification).filter_by(offer_id=offer.id).first()
    if not verification or not verification.dropship_order_ready(): return "SUPPLIER_FACTS_UNVERIFIED", verification
    quantity = max(1, int(item.quantity or 1))
    if int(offer.supply_price_krw or 0) <= 0: return "SUPPLY_PRICE_UNKNOWN", verification
    if int(offer.moq or 1) > quantity: return "MOQ_NOT_SUPPORTED", verification
    if offer.stock_qty is None: return "SUPPLIER_STOCK_UNKNOWN", verification
    if int(offer.stock_qty) < quantity: return "SUPPLIER_STOCK_SHORTAGE", verification
    return "", verification


def _set_item_exception(item: OSSalesOrderItem, code: str) -> None:
    item.status = "exception"
    item.exception_code = code


def request_order_fulfillment(order_item_id: int, *, actor: str = "user") -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        item = db.query(OSSalesOrderItem).filter_by(id=int(order_item_id)).first()
        if not item: return {"ok": False, "error": "주문 품목을 찾을 수 없습니다."}
        if not item.product_id:
            _set_item_exception(item, "UNLINKED_PRODUCT"); db.commit(); return {"ok": False, "error": "내부 상품과 연결되지 않은 주문입니다."}
        if item.status in {"ordered", "shipped", "completed", "cancelled"}: return {"ok": False, "error": f"현재 주문품목 상태에서는 새 발주 요청을 만들 수 없습니다: {item.status}"}
        offer, selection_error = _select_supplier_offer(db, item)
        if not offer:
            _set_item_exception(item, selection_error or "NO_SUPPLIER_OFFER"); db.commit()
            messages = {"SUPPLIER_SELECTION_REQUIRED": "공급처 후보가 여러 개입니다. 공급처를 먼저 선택하세요.", "SUPPLIER_VARIANT_MISMATCH": "주문 옵션과 선택된 공급처 옵션이 일치하지 않습니다.", "NO_VARIANT_OFFER": "주문 옵션에 맞는 공급처 상품 옵션이 없습니다."}
            return {"ok": False, "error": messages.get(selection_error, "사용 가능한 공급처 상품이 없습니다.")}
        item.supplier_offer_id = offer.id
        validation_error, verification = _validate_offer_for_order(db, item, offer)
        if validation_error:
            _set_item_exception(item, validation_error); db.commit()
            messages = {"SUPPLIER_FACTS_UNVERIFIED": "공급가·배송비·재고·MOQ·옵션 식별정보가 모두 검증되지 않아 실제 발주 승인을 차단했습니다.", "SUPPLY_PRICE_UNKNOWN": "공급가가 확인되지 않아 실제 발주를 승인할 수 없습니다.", "MOQ_NOT_SUPPORTED": "공급처 최소주문수량(MOQ)이 고객 주문수량보다 큽니다.", "SUPPLIER_STOCK_UNKNOWN": "공급처 재고가 확인되지 않아 실제 발주를 승인할 수 없습니다.", "SUPPLIER_STOCK_SHORTAGE": "공급처 재고가 고객 주문수량보다 부족합니다."}
            return {"ok": False, "error": messages[validation_error], "code": validation_error}
        if item.status in {"new", "exception"}: item.status = "ready"; item.exception_code = ""
        supplier = db.query(OSSupplier).filter_by(id=offer.supplier_id).first()
        fulfillment = db.query(OSFulfillment).filter_by(order_item_id=item.id).first()
        if fulfillment and fulfillment.status in {"ordered", "shipping", "shipped", "completed"}: return {"ok": True, "already_ordered": True, "fulfillment_id": fulfillment.id}
        if not fulfillment:
            fulfillment = OSFulfillment(order_item_id=item.id, supplier_offer_id=offer.id, supplier_code=supplier.code if supplier else "", status="pending_approval", quantity=max(1, int(item.quantity or 1)), supply_cost_krw=int(offer.supply_price_krw or 0) * max(1, int(item.quantity or 1)), shipping_cost_krw=int(offer.shipping_fee_krw or 0)); db.add(fulfillment); db.flush()
        elif fulfillment.status == "failed":
            FULFILLMENT_STATES.require("failed", "pending_approval"); fulfillment.status = "pending_approval"; fulfillment.failure_code = ""; fulfillment.failure_message = ""; fulfillment.supplier_offer_id = offer.id
        quantity = max(1, int(item.quantity or 1)); fulfillment_id = int(fulfillment.id); supplier_name = supplier.name if supplier else "공급처"; product_name = item.product_name
        payload = {"order_item_id": int(order_item_id), "fulfillment_id": fulfillment_id, "supplier_offer_id": int(offer.id), "supplier_offer_verification_id": int(verification.id) if verification else None, "supplier_code": supplier.code if supplier else "", "supplier_product_id": str(offer.supplier_product_id or ""), "supplier_variant_id": str(offer.supplier_variant_id or ""), "variant_id": int(item.variant_id) if item.variant_id else None, "quantity": quantity, "expected_supply_cost_krw": int(offer.supply_price_krw or 0) * quantity, "expected_shipping_cost_krw": int(offer.shipping_fee_krw or 0), "offer_last_synced_at": offer.last_synced_at.isoformat() if offer.last_synced_at else None, "commercial_facts_verified_at": verification.verified_at.isoformat() if verification and verification.verified_at else None}
        db.commit()
    approval = request_approval(action_type="supplier.order", entity_type="fulfillment", entity_id=fulfillment_id, payload=payload, summary=f"{supplier_name}에 '{product_name}' {quantity}개 실제 발주 · 예상 {payload['expected_supply_cost_krw'] + payload['expected_shipping_cost_krw']:,}원", risk_level="critical", requested_by=actor, ttl_minutes=30)
    return {"ok": True, "fulfillment_id": fulfillment_id, **approval}


def approve_fulfillment_state(approval_id: int) -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        approval = db.query(OSApprovalRequest).filter_by(id=int(approval_id)).first()
        if not approval or approval.action_type != "supplier.order": return {"ok": False, "error": "공급처 발주 승인 요청이 아닙니다."}
        if approval.status != "approved": return {"ok": False, "error": "먼저 승인해야 합니다."}
        payload = json.loads(approval.payload_json or "{}")
        fulfillment = db.query(OSFulfillment).filter_by(id=int(payload.get("fulfillment_id", 0))).first()
        if not fulfillment: return {"ok": False, "error": "Fulfillment 없음"}
        if fulfillment.status == "pending_approval": FULFILLMENT_STATES.require(fulfillment.status, "approved"); fulfillment.status = "approved"
        item = db.query(OSSalesOrderItem).filter_by(id=fulfillment.order_item_id).first()
        if item and item.status == "ready": ORDER_ITEM_STATES.require(item.status, "approved"); item.status = "approved"
        fulfillment_id = int(fulfillment.id); status = str(fulfillment.status); db.commit()
        return {"ok": True, "fulfillment_id": fulfillment_id, "status": status, "message": "승인 완료. 검증된 공급처 주문 드라이버가 있는 경우에만 자동 실행 대상이 됩니다."}
