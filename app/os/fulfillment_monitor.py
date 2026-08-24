"""Read model for order / supplier-order / payment / tracking operations monitoring."""
from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.db import get_db
from app.os.drivers import supplier_driver_status
from app.os.models import OSFulfillment, OSSalesOrder, OSSalesOrderItem
from app.os.schema import ensure_os_schema


def _payment_phase(fulfillment: OSFulfillment | None) -> tuple[str, str]:
    """Return a truthful payment-stage label without pretending card approval exists yet."""
    if fulfillment is None:
        return "not_prepared", "발주 준비 전"
    if fulfillment.status == "pending_approval":
        return "approval_wait", "발주 승인/정책 확인"
    if fulfillment.status == "approved":
        return "payment_ready", "결제 준비"
    if fulfillment.status == "ordering":
        return "payment_processing", "공급처 주문·결제 처리중"
    if fulfillment.status in {"ordered", "shipping", "shipped", "completed"}:
        # Current schema does not persist a separate payment confirmation record.
        # Do not claim card payment specifically; supplier order creation is confirmed.
        return "supplier_order_confirmed", "공급처 주문 생성 확인"
    if fulfillment.status == "failed":
        return "failed", "발주/결제 실패"
    if fulfillment.status == "cancelled":
        return "cancelled", "취소"
    return "unknown", fulfillment.status


def _tracking_phase(fulfillment: OSFulfillment | None) -> tuple[str, str]:
    if fulfillment is None or not fulfillment.supplier_order_id:
        return "waiting_order", "발주 전"
    if fulfillment.invoice_registered:
        return "marketplace_done", "판매채널 송장반영 완료"
    if fulfillment.tracking_number:
        return "tracking_ready", "송장 확인 · 채널반영 대기"
    if fulfillment.status in {"ordered", "shipping"}:
        return "waiting_tracking", "공급처 송장 대기"
    if fulfillment.status == "failed":
        return "failed", "확인 필요"
    return "waiting_tracking", "송장 대기"


def get_fulfillment_monitor(limit: int = 500) -> dict[str, Any]:
    ensure_os_schema()
    settings = get_settings()

    with get_db() as db:
        items = (
            db.query(OSSalesOrderItem)
            .order_by(OSSalesOrderItem.id.desc())
            .limit(max(1, int(limit)))
            .all()
        )
        order_ids = list({int(x.order_id) for x in items})
        orders = {
            int(x.id): x
            for x in db.query(OSSalesOrder).filter(OSSalesOrder.id.in_(order_ids or [-1])).all()
        }
        item_ids = [int(x.id) for x in items]
        fulfillments = {
            int(x.order_item_id): x
            for x in db.query(OSFulfillment).filter(OSFulfillment.order_item_id.in_(item_ids or [-1])).all()
        }

        rows: list[dict[str, Any]] = []
        metrics = {
            "total": 0,
            "new": 0,
            "approval_wait": 0,
            "payment_wait": 0,
            "ordered": 0,
            "tracking_wait": 0,
            "tracking_done": 0,
            "exceptions": 0,
        }

        for item in items:
            order = orders.get(int(item.order_id))
            if not order:
                continue
            fulfillment = fulfillments.get(int(item.id))
            payment_code, payment_label = _payment_phase(fulfillment)
            tracking_code, tracking_label = _tracking_phase(fulfillment)
            supplier_code = str(fulfillment.supplier_code or "").strip().lower() if fulfillment else ""
            driver = supplier_driver_status(supplier_code) if supplier_code else {
                "registered": False,
                "verified": False,
                "can_create_order": False,
                "note": "공급처 미선택",
            }

            sale_amount = int(item.unit_sale_price_krw or 0) * max(1, int(item.quantity or 1))
            expected_cost = 0
            if fulfillment:
                expected_cost = int(fulfillment.supply_cost_krw or 0) + int(fulfillment.shipping_cost_krw or 0)

            error = str(item.exception_code or "")
            if fulfillment and fulfillment.failure_message:
                error = str(fulfillment.failure_message)

            row = {
                "order_item_id": int(item.id),
                "order_id": int(order.id),
                "platform": str(order.platform or ""),
                "order_no": str(order.external_order_id or ""),
                "external_item_id": str(item.external_item_id or ""),
                "product_name": str(item.product_name or ""),
                "quantity": int(item.quantity or 1),
                "sale_amount_krw": sale_amount,
                "receiver_name": str(order.receiver_name or ""),
                "ordered_at": order.ordered_at,
                "order_status": str(order.status or ""),
                "item_status": str(item.status or ""),
                "supplier_code": supplier_code,
                "fulfillment_id": int(fulfillment.id) if fulfillment else None,
                "fulfillment_status": str(fulfillment.status or "") if fulfillment else "",
                "supplier_order_id": str(fulfillment.supplier_order_id or "") if fulfillment else "",
                "expected_cost_krw": expected_cost,
                "payment_code": payment_code,
                "payment_label": payment_label,
                "tracking_code": tracking_code,
                "tracking_label": tracking_label,
                "delivery_company": str(fulfillment.delivery_company or "") if fulfillment else "",
                "tracking_number": str(fulfillment.tracking_number or "") if fulfillment else "",
                "invoice_registered": bool(fulfillment.invoice_registered) if fulfillment else False,
                "driver_verified": bool(driver.get("verified")),
                "driver_can_order": bool(driver.get("can_create_order")),
                "driver_note": str(driver.get("note") or ""),
                "error": error,
            }
            rows.append(row)

            metrics["total"] += 1
            if item.status == "new":
                metrics["new"] += 1
            if payment_code == "approval_wait":
                metrics["approval_wait"] += 1
            if payment_code in {"payment_ready", "payment_processing"}:
                metrics["payment_wait"] += 1
            if fulfillment and fulfillment.status in {"ordered", "shipping", "shipped", "completed"}:
                metrics["ordered"] += 1
            if tracking_code in {"waiting_tracking", "tracking_ready"}:
                metrics["tracking_wait"] += 1
            if tracking_code == "marketplace_done":
                metrics["tracking_done"] += 1
            if error or item.status == "exception" or (fulfillment and fulfillment.status == "failed"):
                metrics["exceptions"] += 1

    return {
        "metrics": metrics,
        "rows": rows,
        "policy": {
            "auto_purchase_enabled": bool(settings.fulfillment_auto_purchase_enabled),
            "auto_tracking_enabled": bool(settings.fulfillment_auto_tracking_enabled),
            "poll_interval_seconds": int(settings.fulfillment_poll_interval_seconds),
            "max_order_krw": int(settings.fulfillment_max_order_krw),
            "min_profit_krw": int(settings.fulfillment_min_profit_krw),
            "min_margin_pct": float(settings.fulfillment_min_margin_pct),
            "supplier_allowlist": str(settings.fulfillment_supplier_allowlist or ""),
        },
        "payment_model": {
            "interactive_card_supported": False,
            "note": "현재 별도 카드사 앱 승인 상태는 아직 영속화되지 않았습니다. 공급처 주문 생성 상태와 분리된 Payment Orchestrator가 다음 단계입니다.",
        },
    }
