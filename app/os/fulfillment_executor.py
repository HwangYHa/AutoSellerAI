"""Verified supplier-order execution service.

This module is the only v3 path allowed to call a supplier order driver. It is
intended for the ``dangerous`` RQ worker after an explicit supplier.order approval.
"""
from __future__ import annotations

import json
from datetime import datetime

from app.db import get_db
from app.os.approvals import execute_idempotent, make_idempotency_key
from app.os.drivers import get_supplier_order_driver
from app.os.models import OSApprovalRequest, OSFulfillment, OSSalesOrder, OSSalesOrderItem, OSSupplierOffer
from app.os.ports import SupplierOrderCommand
from app.os.quality_models import OSOfferVerification
from app.os.schema import ensure_os_schema
from app.os.state import FULFILLMENT_STATES, ORDER_ITEM_STATES


def execute_supplier_order(approval_id: int, *, actor: str = "worker") -> dict:
    ensure_os_schema()
    with get_db() as db:
        approval = db.query(OSApprovalRequest).filter_by(id=int(approval_id)).first()
        if not approval or approval.action_type != "supplier.order":
            return {"ok": False, "error": "공급처 발주 승인이 아닙니다."}
        if approval.status not in {"approved", "consumed"}:
            return {"ok": False, "error": f"실행 가능한 승인 상태가 아닙니다: {approval.status}"}
        try:
            payload = json.loads(approval.payload_json or "{}")
        except Exception:
            return {"ok": False, "error": "승인 payload가 손상되었습니다."}

        fulfillment = db.query(OSFulfillment).filter_by(id=int(payload.get("fulfillment_id") or 0)).first()
        if not fulfillment:
            return {"ok": False, "error": "Fulfillment를 찾을 수 없습니다."}
        if fulfillment.status in {"ordered", "shipping", "shipped", "completed"} and fulfillment.supplier_order_id:
            return {
                "ok": True,
                "reused": True,
                "fulfillment_id": fulfillment.id,
                "supplier_order_id": fulfillment.supplier_order_id,
                "status": fulfillment.status,
            }
        if fulfillment.status not in {"approved", "ordering", "failed"}:
            return {"ok": False, "error": f"현재 Fulfillment 상태에서는 실행할 수 없습니다: {fulfillment.status}"}

        item = db.query(OSSalesOrderItem).filter_by(id=fulfillment.order_item_id).first()
        if not item:
            return {"ok": False, "error": "주문 품목을 찾을 수 없습니다."}
        order = db.query(OSSalesOrder).filter_by(id=item.order_id).first()
        offer = db.query(OSSupplierOffer).filter_by(id=fulfillment.supplier_offer_id).first() if fulfillment.supplier_offer_id else None
        if not order or not offer:
            return {"ok": False, "error": "주문 또는 공급처 Offer가 연결되지 않았습니다."}

        verification = db.query(OSOfferVerification).filter_by(offer_id=offer.id).first()
        if not verification or not verification.dropship_order_ready():
            return {"ok": False, "error": "공급처 상업정보 검증 상태가 유효하지 않아 실제 발주를 중단했습니다."}
        approved_verification_id = int(payload.get("supplier_offer_verification_id") or 0)
        if approved_verification_id and approved_verification_id != int(verification.id):
            return {"ok": False, "error": "승인 이후 공급처 검증 레코드가 변경되었습니다. 새 승인이 필요합니다."}

        # Approval payload freezes the exact commercial terms the user reviewed.
        if int(payload.get("supplier_offer_id") or 0) != int(offer.id):
            return {"ok": False, "error": "승인 이후 공급처 Offer 연결이 변경되었습니다. 새 승인이 필요합니다."}
        if int(payload.get("quantity") or 0) != int(item.quantity or 0):
            return {"ok": False, "error": "승인 이후 주문 수량이 변경되었습니다. 새 승인이 필요합니다."}
        expected_supply = int(payload.get("expected_supply_cost_krw") or 0)
        current_supply = int(offer.supply_price_krw or 0) * max(1, int(item.quantity or 1))
        expected_shipping = int(payload.get("expected_shipping_cost_krw") or 0)
        current_shipping = int(offer.shipping_fee_krw or 0)
        if expected_supply != current_supply or expected_shipping != current_shipping:
            return {"ok": False, "error": "승인 이후 공급가/배송비가 변경되었습니다. 새 승인이 필요합니다."}
        if int(offer.moq or 1) > int(item.quantity or 1):
            return {"ok": False, "error": "공급처 MOQ 조건이 주문수량과 맞지 않아 발주를 중단했습니다."}
        if offer.stock_qty is None:
            return {"ok": False, "error": "공급처 재고를 확인할 수 없어 발주를 중단했습니다."}
        if int(offer.stock_qty) < int(item.quantity or 1):
            return {"ok": False, "error": "공급처 재고가 부족해 발주를 중단했습니다."}

        supplier_code = str(payload.get("supplier_code") or fulfillment.supplier_code or "").strip().lower()
        driver = get_supplier_order_driver(supplier_code, require_verified=True)
        if not driver:
            return {"ok": False, "error": f"{supplier_code or '해당 공급처'}의 검증된 v3 주문 드라이버가 없습니다."}
        if not driver.can_create_order():
            return {"ok": False, "error": f"{supplier_code} 주문 드라이버가 현재 발주 가능 상태가 아닙니다."}

        op_payload = dict(payload)
        idempotency_key = make_idempotency_key("supplier.order", "fulfillment", str(fulfillment.id), op_payload)
        command = SupplierOrderCommand(
            order_item_id=item.id,
            supplier_product_id=str(offer.supplier_product_id or ""),
            supplier_variant_id=str(offer.supplier_variant_id or ""),
            quantity=max(1, int(item.quantity or 1)),
            receiver_name=order.receiver_name or "",
            receiver_phone=order.receiver_phone or "",
            address=order.shipping_address or "",
            shipping_message=order.shipping_message or "",
            idempotency_key=idempotency_key,
        )
        validation_errors = list(driver.validate(command) or [])
        if validation_errors:
            return {"ok": False, "error": " / ".join(validation_errors[:10])}

        if fulfillment.status in {"approved", "failed"}:
            if fulfillment.status == "failed":
                FULFILLMENT_STATES.require("failed", "pending_approval")
                fulfillment.status = "pending_approval"
                FULFILLMENT_STATES.require("pending_approval", "approved")
                fulfillment.status = "approved"
            FULFILLMENT_STATES.require(fulfillment.status, "ordering")
            fulfillment.status = "ordering"
            fulfillment.failure_code = ""
            fulfillment.failure_message = ""
            db.commit()

    def executor():
        simulation = driver.simulate(command)
        result = driver.create_order(command, simulation=simulation)
        if not result.ok or not result.supplier_order_id:
            raise RuntimeError(result.error or "공급처 주문 생성 실패")
        return {
            "supplier_order_id": result.supplier_order_id,
            "status": result.status,
            "amount_krw": result.amount_krw,
            "delivery_company": result.delivery_company,
            "tracking_number": result.tracking_number,
            "raw": result.raw,
        }

    execution = execute_idempotent(
        action_type="supplier.order",
        entity_type="fulfillment",
        entity_id=str(payload["fulfillment_id"]),
        payload=op_payload,
        executor=executor,
        approval_id=int(approval_id),
        require_approval=True,
        actor=actor,
    )

    with get_db() as db:
        fulfillment = db.query(OSFulfillment).filter_by(id=int(payload["fulfillment_id"])).first()
        item = db.query(OSSalesOrderItem).filter_by(id=fulfillment.order_item_id).first() if fulfillment else None
        if fulfillment:
            if execution.get("ok"):
                response = execution.get("response") or {}
                if fulfillment.status == "ordering":
                    FULFILLMENT_STATES.require("ordering", "ordered")
                fulfillment.status = "ordered"
                fulfillment.supplier_order_id = str(response.get("supplier_order_id") or "")
                fulfillment.ordered_at = datetime.utcnow()
                fulfillment.delivery_company = str(response.get("delivery_company") or "")
                fulfillment.tracking_number = str(response.get("tracking_number") or "")
                actual = int(response.get("amount_krw") or 0)
                if actual > 0:
                    fulfillment.supply_cost_krw = actual
                if item and item.status == "approved":
                    ORDER_ITEM_STATES.require("approved", "ordered")
                    item.status = "ordered"
            else:
                fulfillment.status = "failed"
                fulfillment.failure_code = "SUPPLIER_ORDER_FAILED"
                fulfillment.failure_message = str(execution.get("error") or "")[:1000]
                if item and item.status == "approved":
                    ORDER_ITEM_STATES.require("approved", "exception")
                    item.status = "exception"
                    item.exception_code = "SUPPLIER_ORDER_FAILED"
            db.commit()
    return execution
