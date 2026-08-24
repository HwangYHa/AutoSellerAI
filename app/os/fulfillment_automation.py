"""End-to-end order fulfillment automation.

Pipeline:
marketplace order -> Seller OS order item -> verified supplier offer -> policy gate ->
verified supplier driver -> supplier order/payment -> tracking poll -> marketplace dispatch.

The engine never invents a supplier order capability. Automatic purchase is only
allowed when the operator explicitly enables it and the supplier has a verified
SupplierOrderPort registered in app.os.drivers.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import get_settings
from app.db import get_db
from app.os.approvals import decide_approval, execute_idempotent
from app.os.drivers import get_supplier_order_driver, supplier_driver_status
from app.os.models import OSApprovalRequest, OSFulfillment, OSSalesOrder, OSSalesOrderItem
from app.os.schema import ensure_os_schema
from app.os.state import FULFILLMENT_STATES, ORDER_ITEM_STATES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoPurchasePolicyResult:
    allowed: bool
    code: str
    reason: str
    sale_amount_krw: int = 0
    expected_cost_krw: int = 0
    expected_profit_krw: int = 0
    margin_pct: float = 0.0


def _json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _supplier_allowlist() -> set[str]:
    raw = str(get_settings().fulfillment_supplier_allowlist or "")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def evaluate_auto_purchase_policy(approval_id: int) -> AutoPurchasePolicyResult:
    """Evaluate whether a pending supplier order may be auto-approved and paid."""
    settings = get_settings()
    if not settings.fulfillment_auto_purchase_enabled:
        return AutoPurchasePolicyResult(False, "AUTO_PURCHASE_DISABLED", "자동발주/결제가 비활성화되어 있습니다.")

    ensure_os_schema()
    with get_db() as db:
        approval = db.query(OSApprovalRequest).filter_by(id=int(approval_id)).first()
        if not approval or approval.action_type != "supplier.order":
            return AutoPurchasePolicyResult(False, "INVALID_APPROVAL", "공급처 발주 승인 요청이 아닙니다.")
        if approval.status not in {"pending", "approved"}:
            return AutoPurchasePolicyResult(False, "APPROVAL_NOT_PENDING", f"현재 승인 상태: {approval.status}")

        payload = _json(approval.payload_json)
        fulfillment = db.query(OSFulfillment).filter_by(id=int(payload.get("fulfillment_id") or 0)).first()
        if not fulfillment:
            return AutoPurchasePolicyResult(False, "FULFILLMENT_MISSING", "Fulfillment를 찾을 수 없습니다.")
        item = db.query(OSSalesOrderItem).filter_by(id=fulfillment.order_item_id).first()
        order = db.query(OSSalesOrder).filter_by(id=item.order_id).first() if item else None
        if not item or not order:
            return AutoPurchasePolicyResult(False, "ORDER_MISSING", "주문 또는 주문 품목을 찾을 수 없습니다.")

        if not order.receiver_name or not order.receiver_phone or not order.shipping_address:
            return AutoPurchasePolicyResult(False, "RECEIVER_INCOMPLETE", "수령인 이름/전화번호/배송지가 완전하지 않습니다.")

        supplier_code = str(payload.get("supplier_code") or fulfillment.supplier_code or "").strip().lower()
        driver_state = supplier_driver_status(supplier_code)
        if not driver_state.get("verified") or not driver_state.get("can_create_order"):
            return AutoPurchasePolicyResult(
                False,
                "DRIVER_NOT_READY",
                f"{supplier_code or '공급처'} 실제 발주/결제 드라이버가 검증 완료 상태가 아닙니다.",
            )

        allowlist = _supplier_allowlist()
        if allowlist and supplier_code not in allowlist:
            return AutoPurchasePolicyResult(False, "SUPPLIER_NOT_ALLOWED", f"자동발주 허용 공급처가 아닙니다: {supplier_code}")

        quantity = max(1, int(item.quantity or 1))
        sale_amount = max(0, int(item.unit_sale_price_krw or 0)) * quantity
        expected_cost = int(payload.get("expected_supply_cost_krw") or 0) + int(payload.get("expected_shipping_cost_krw") or 0)
        profit = sale_amount - expected_cost
        margin = (profit / sale_amount) if sale_amount > 0 else -1.0

        if expected_cost <= 0:
            return AutoPurchasePolicyResult(False, "COST_UNKNOWN", "예상 공급가/배송비가 확인되지 않았습니다.", sale_amount, expected_cost, profit, margin)
        if expected_cost > int(settings.fulfillment_max_order_krw):
            return AutoPurchasePolicyResult(
                False,
                "ORDER_LIMIT_EXCEEDED",
                f"자동발주 한도 초과: {expected_cost:,}원 > {int(settings.fulfillment_max_order_krw):,}원",
                sale_amount, expected_cost, profit, margin,
            )
        if profit < int(settings.fulfillment_min_profit_krw):
            return AutoPurchasePolicyResult(
                False,
                "MIN_PROFIT_NOT_MET",
                f"예상 이익 부족: {profit:,}원",
                sale_amount, expected_cost, profit, margin,
            )
        if margin < float(settings.fulfillment_min_margin_pct):
            return AutoPurchasePolicyResult(
                False,
                "MIN_MARGIN_NOT_MET",
                f"예상 마진율 부족: {margin:.1%}",
                sale_amount, expected_cost, profit, margin,
            )

        return AutoPurchasePolicyResult(
            True,
            "OK",
            "자동발주 정책 통과",
            sale_amount,
            expected_cost,
            profit,
            margin,
        )


def _queue_supplier_order(approval_id: int, fulfillment_id: int) -> dict[str, Any]:
    from app.os.operations import approve_fulfillment_state
    from app.os.tasks import enqueue_task

    decided = decide_approval(approval_id, approve=True, actor="auto-fulfillment-policy")
    if not decided.get("ok") and "이미 처리" not in str(decided.get("error") or ""):
        return {"ok": False, "error": decided.get("error") or "자동 승인 실패"}

    state = approve_fulfillment_state(approval_id)
    if not state.get("ok"):
        return {"ok": False, "error": state.get("error") or "Fulfillment 승인 상태 전이 실패"}

    queued = enqueue_task(
        "supplier_order",
        {"approval_id": int(approval_id)},
        queue_name="dangerous",
        dedupe_key=f"supplier_order:{int(fulfillment_id)}",
    )
    return {"ok": bool(queued.get("ok")), "approval_id": approval_id, "fulfillment_id": fulfillment_id, "task": queued}


def process_new_order_items(limit: int | None = None) -> dict[str, Any]:
    """Create fulfillment approvals and auto-queue eligible purchases."""
    settings = get_settings()
    max_items = max(1, int(limit or settings.fulfillment_max_items_per_cycle))
    ensure_os_schema()

    with get_db() as db:
        ids = [
            int(x.id)
            for x in (
                db.query(OSSalesOrderItem)
                .filter(OSSalesOrderItem.status.in_(["new", "exception", "ready"]))
                .order_by(OSSalesOrderItem.id.asc())
                .limit(max_items)
                .all()
            )
        ]

    stats: dict[str, Any] = {
        "scanned": len(ids),
        "approval_ready": 0,
        "auto_queued": 0,
        "manual_or_blocked": 0,
        "errors": 0,
        "details": [],
    }

    from app.os.operations import request_order_fulfillment

    for item_id in ids:
        try:
            requested = request_order_fulfillment(item_id, actor="auto-fulfillment")
            if not requested.get("ok"):
                stats["manual_or_blocked"] += 1
                stats["details"].append({"order_item_id": item_id, "status": "blocked", "error": requested.get("error"), "code": requested.get("code")})
                continue
            if requested.get("already_ordered"):
                continue
            approval_id = int(requested.get("approval_id") or 0)
            fulfillment_id = int(requested.get("fulfillment_id") or 0)
            if approval_id <= 0 or fulfillment_id <= 0:
                stats["errors"] += 1
                stats["details"].append({"order_item_id": item_id, "status": "error", "error": "approval/fulfillment id missing"})
                continue
            stats["approval_ready"] += 1

            policy = evaluate_auto_purchase_policy(approval_id)
            if not policy.allowed:
                stats["manual_or_blocked"] += 1
                stats["details"].append({
                    "order_item_id": item_id,
                    "fulfillment_id": fulfillment_id,
                    "approval_id": approval_id,
                    "status": "pending_manual",
                    "policy_code": policy.code,
                    "reason": policy.reason,
                    "expected_cost_krw": policy.expected_cost_krw,
                    "expected_profit_krw": policy.expected_profit_krw,
                })
                continue

            queued = _queue_supplier_order(approval_id, fulfillment_id)
            if queued.get("ok"):
                stats["auto_queued"] += 1
                stats["details"].append({
                    "order_item_id": item_id,
                    "fulfillment_id": fulfillment_id,
                    "approval_id": approval_id,
                    "status": "auto_queued",
                    "expected_cost_krw": policy.expected_cost_krw,
                    "expected_profit_krw": policy.expected_profit_krw,
                    "margin_pct": policy.margin_pct,
                })
            else:
                stats["errors"] += 1
                stats["details"].append({"order_item_id": item_id, "status": "queue_failed", "error": queued.get("error")})
        except Exception as exc:
            logger.exception("auto fulfillment item failed order_item_id=%s", item_id)
            stats["errors"] += 1
            stats["details"].append({"order_item_id": item_id, "status": "error", "error": f"{type(exc).__name__}: {exc}"})

    return stats


def _register_marketplace_tracking(order: OSSalesOrder, item: OSSalesOrderItem, fulfillment: OSFulfillment) -> dict[str, Any]:
    platform = str(order.platform or "").strip().lower()
    delivery_company = str(fulfillment.delivery_company or "").strip()
    tracking_number = str(fulfillment.tracking_number or "").strip()
    if not delivery_company or not tracking_number:
        return {"ok": False, "error": "택배사 또는 송장번호가 없습니다."}

    payload = {
        "platform": platform,
        "external_order_id": str(order.external_order_id or ""),
        "external_item_id": str(item.external_item_id or ""),
        "delivery_company": delivery_company,
        "tracking_number": tracking_number,
    }

    def executor() -> dict[str, Any]:
        if platform == "coupang":
            from app.platforms.coupang import get_coupang_uploader
            result = get_coupang_uploader().register_shipment(
                str(order.external_order_id),
                str(item.external_item_id),
                delivery_company,
                tracking_number,
            )
        elif platform == "smartstore":
            from app.platforms.smartstore import get_smartstore_uploader
            result = get_smartstore_uploader().dispatch_product_order(
                str(item.external_item_id),
                delivery_company,
                tracking_number,
            )
        else:
            raise RuntimeError(f"송장 자동등록을 지원하지 않는 판매채널입니다: {platform}")
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "판매채널 송장 등록 실패")
        return result

    return execute_idempotent(
        action_type="marketplace.tracking",
        entity_type="fulfillment",
        entity_id=str(fulfillment.id),
        payload=payload,
        executor=executor,
        require_approval=False,
        actor="auto-fulfillment",
    )


def sync_supplier_tracking(limit: int | None = None) -> dict[str, Any]:
    """Poll supplier orders and immediately dispatch tracking to the marketplace."""
    settings = get_settings()
    if not settings.fulfillment_auto_tracking_enabled:
        return {"enabled": False, "checked": 0, "tracking_found": 0, "marketplace_updated": 0, "errors": 0}

    max_items = max(1, int(limit or settings.fulfillment_max_items_per_cycle))
    ensure_os_schema()
    with get_db() as db:
        rows = (
            db.query(OSFulfillment)
            .filter(
                OSFulfillment.status.in_(["ordered", "shipping"]),
                OSFulfillment.supplier_order_id != "",
            )
            .order_by(OSFulfillment.id.asc())
            .limit(max_items)
            .all()
        )
        ids = [int(x.id) for x in rows]

    stats: dict[str, Any] = {"enabled": True, "checked": 0, "tracking_found": 0, "marketplace_updated": 0, "errors": 0, "details": []}

    for fulfillment_id in ids:
        try:
            with get_db() as db:
                fulfillment = db.query(OSFulfillment).filter_by(id=fulfillment_id).first()
                if not fulfillment:
                    continue
                item = db.query(OSSalesOrderItem).filter_by(id=fulfillment.order_item_id).first()
                order = db.query(OSSalesOrder).filter_by(id=item.order_id).first() if item else None
                if not item or not order:
                    continue
                supplier_code = str(fulfillment.supplier_code or "").strip().lower()
                supplier_order_id = str(fulfillment.supplier_order_id or "").strip()
                already_registered = bool(fulfillment.invoice_registered)

            driver = get_supplier_order_driver(supplier_code, require_verified=True)
            if not driver:
                stats["errors"] += 1
                stats["details"].append({"fulfillment_id": fulfillment_id, "status": "driver_not_ready", "supplier": supplier_code})
                continue

            stats["checked"] += 1
            tracking = driver.get_tracking(supplier_order_id)
            if not tracking.ok:
                stats["errors"] += 1
                stats["details"].append({"fulfillment_id": fulfillment_id, "status": "tracking_error", "error": tracking.error})
                continue
            if not tracking.tracking_number:
                if str(tracking.status or "").lower() in {"shipping", "in_transit"}:
                    with get_db() as db:
                        row = db.query(OSFulfillment).filter_by(id=fulfillment_id).first()
                        if row and row.status == "ordered":
                            FULFILLMENT_STATES.require("ordered", "shipping")
                            row.status = "shipping"
                            db.commit()
                continue

            stats["tracking_found"] += 1
            with get_db() as db:
                fulfillment = db.query(OSFulfillment).filter_by(id=fulfillment_id).first()
                item = db.query(OSSalesOrderItem).filter_by(id=fulfillment.order_item_id).first() if fulfillment else None
                order = db.query(OSSalesOrder).filter_by(id=item.order_id).first() if item else None
                if not fulfillment or not item or not order:
                    continue
                fulfillment.delivery_company = str(tracking.delivery_company or fulfillment.delivery_company or "")
                fulfillment.tracking_number = str(tracking.tracking_number)
                if fulfillment.status == "ordered":
                    FULFILLMENT_STATES.require("ordered", "shipping")
                    fulfillment.status = "shipping"
                db.commit()
                already_registered = bool(fulfillment.invoice_registered)

            if already_registered:
                continue

            with get_db() as db:
                fulfillment = db.query(OSFulfillment).filter_by(id=fulfillment_id).first()
                item = db.query(OSSalesOrderItem).filter_by(id=fulfillment.order_item_id).first() if fulfillment else None
                order = db.query(OSSalesOrder).filter_by(id=item.order_id).first() if item else None
                if not fulfillment or not item or not order:
                    continue
                registration = _register_marketplace_tracking(order, item, fulfillment)

            if not registration.get("ok"):
                stats["errors"] += 1
                stats["details"].append({"fulfillment_id": fulfillment_id, "status": "marketplace_dispatch_failed", "error": registration.get("error")})
                continue

            with get_db() as db:
                fulfillment = db.query(OSFulfillment).filter_by(id=fulfillment_id).first()
                item = db.query(OSSalesOrderItem).filter_by(id=fulfillment.order_item_id).first() if fulfillment else None
                if fulfillment:
                    fulfillment.invoice_registered = True
                    if fulfillment.status == "shipping":
                        FULFILLMENT_STATES.require("shipping", "shipped")
                    elif fulfillment.status == "ordered":
                        FULFILLMENT_STATES.require("ordered", "shipped")
                    fulfillment.status = "shipped"
                    fulfillment.shipped_at = fulfillment.shipped_at or datetime.utcnow()
                if item and item.status == "ordered":
                    ORDER_ITEM_STATES.require("ordered", "shipped")
                    item.status = "shipped"
                db.commit()
            stats["marketplace_updated"] += 1
            stats["details"].append({"fulfillment_id": fulfillment_id, "status": "shipped", "tracking_number": tracking.tracking_number})
        except Exception as exc:
            logger.exception("tracking sync failed fulfillment_id=%s", fulfillment_id)
            stats["errors"] += 1
            stats["details"].append({"fulfillment_id": fulfillment_id, "status": "error", "error": f"{type(exc).__name__}: {exc}"})

    return stats


def run_fulfillment_cycle(limit: int | None = None) -> dict[str, Any]:
    """Run one complete automatic fulfillment iteration."""
    return {
        "purchase": process_new_order_items(limit=limit),
        "tracking": sync_supplier_tracking(limit=limit),
    }
