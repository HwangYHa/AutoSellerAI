"""Supplier payment orchestration with explicit human card-app authorization states."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.db import get_db
from app.os.commerce_automation_models import OSPaymentSession
from app.os.drivers import get_supplier_order_driver
from app.os.models import OSFulfillment, OSSalesOrderItem
from app.os.ports import SupplierOrderCommand, SupplierPaymentPort
from app.os.schema import ensure_os_schema
from app.os.state import FULFILLMENT_STATES, ORDER_ITEM_STATES


def prepare_payment(
    fulfillment_id: int,
    *,
    driver: Any,
    command: SupplierOrderCommand,
    simulation: dict[str, Any] | None = None,
    expected_amount_krw: int = 0,
) -> dict[str, Any]:
    """Prepare payment. Never claims payment completion for an interactive flow."""
    ensure_os_schema()
    if not isinstance(driver, SupplierPaymentPort):
        return {"supported": False, "requires_payment_session": False}

    prepared = driver.prepare_payment(command, simulation=simulation)
    if not prepared.ok:
        return {"supported": True, "ok": False, "error": prepared.error or "결제 준비 실패"}

    mode = str(prepared.payment_mode or "unknown").strip().lower()
    requires_user = bool(prepared.user_action_required or mode == "interactive_card")
    status = "awaiting_user" if requires_user else "authorizing"
    amount = int(prepared.expected_amount_krw or expected_amount_krw or 0)

    with get_db() as db:
        row = db.query(OSPaymentSession).filter_by(fulfillment_id=int(fulfillment_id)).first()
        if not row:
            row = OSPaymentSession(fulfillment_id=int(fulfillment_id))
            db.add(row)
        row.supplier_code = str(getattr(driver, "supplier_code", "") or "").strip().lower()
        row.payment_mode = mode
        row.status = status
        row.expected_amount_krw = amount
        row.payment_url = str(prepared.payment_url or "")
        row.external_payment_id = str(prepared.external_payment_id or "")
        row.user_action_required = requires_user
        row.last_error = ""
        row.metadata_json = json.dumps(
            {"supplier_order_id": prepared.supplier_order_id, "raw": prepared.raw},
            ensure_ascii=False,
            default=str,
        )
        fulfillment = db.query(OSFulfillment).filter_by(id=int(fulfillment_id)).first()
        if fulfillment and prepared.supplier_order_id:
            fulfillment.supplier_order_id = str(prepared.supplier_order_id)
        db.commit()
        db.refresh(row)
        return {
            "supported": True,
            "ok": True,
            "payment_session_id": row.id,
            "payment_mode": row.payment_mode,
            "payment_status": row.status,
            "payment_url": row.payment_url,
            "user_action_required": row.user_action_required,
            "supplier_order_id": prepared.supplier_order_id,
        }


def _mark_fulfillment_paid(db, session: OSPaymentSession, supplier_order_id: str, amount_krw: int) -> None:
    fulfillment = db.query(OSFulfillment).filter_by(id=session.fulfillment_id).first()
    if not fulfillment:
        return
    item = db.query(OSSalesOrderItem).filter_by(id=fulfillment.order_item_id).first()
    if fulfillment.status == "ordering":
        FULFILLMENT_STATES.require("ordering", "ordered")
    fulfillment.status = "ordered"
    fulfillment.supplier_order_id = str(supplier_order_id or fulfillment.supplier_order_id or "")
    fulfillment.ordered_at = fulfillment.ordered_at or datetime.utcnow()
    if int(amount_krw or 0) > 0:
        fulfillment.supply_cost_krw = int(amount_krw)
    if item and item.status == "approved":
        ORDER_ITEM_STATES.require("approved", "ordered")
        item.status = "ordered"


def sync_payment_sessions(limit: int = 100) -> dict[str, Any]:
    """Poll supplier payment states and resume fulfillment after user authorization."""
    ensure_os_schema()
    with get_db() as db:
        ids = [
            int(x.id)
            for x in db.query(OSPaymentSession)
            .filter(OSPaymentSession.status.in_(["awaiting_user", "authorizing"]))
            .order_by(OSPaymentSession.id.asc())
            .limit(max(1, int(limit)))
            .all()
        ]

    stats = {"checked": 0, "paid": 0, "waiting": 0, "failed": 0, "driver_missing": 0, "details": []}
    for session_id in ids:
        with get_db() as db:
            session = db.query(OSPaymentSession).filter_by(id=session_id).first()
            if not session:
                continue
            supplier_code = session.supplier_code
            external_payment_id = session.external_payment_id
            meta = json.loads(session.metadata_json or "{}") if session.metadata_json else {}
            supplier_order_id = str(meta.get("supplier_order_id") or "")

        driver = get_supplier_order_driver(supplier_code, require_verified=True)
        if not driver or not isinstance(driver, SupplierPaymentPort):
            stats["driver_missing"] += 1
            stats["details"].append({"payment_session_id": session_id, "status": "driver_missing"})
            continue

        stats["checked"] += 1
        try:
            result = driver.get_payment_status(external_payment_id, supplier_order_id=supplier_order_id)
        except Exception as exc:
            result = None
            error = f"{type(exc).__name__}: {exc}"
        else:
            error = result.error if result and not result.ok else ""

        with get_db() as db:
            session = db.query(OSPaymentSession).filter_by(id=session_id).first()
            if not session:
                continue
            if not result or not result.ok:
                session.last_error = str(error or "결제 상태 확인 실패")[:2000]
                db.commit()
                stats["failed"] += 1
                continue
            status = str(result.status or "").strip().lower()
            if status == "paid":
                session.status = "paid"
                session.user_action_required = False
                session.actual_amount_krw = int(result.amount_krw or session.expected_amount_krw or 0)
                session.external_payment_id = str(result.external_payment_id or session.external_payment_id or "")
                session.paid_at = datetime.utcnow()
                session.last_error = ""
                _mark_fulfillment_paid(db, session, result.supplier_order_id or supplier_order_id, session.actual_amount_krw)
                db.commit()
                stats["paid"] += 1
            elif status in {"failed", "expired", "cancelled", "refunded"}:
                session.status = status
                session.user_action_required = False
                session.last_error = str(result.error or status)[:2000]
                fulfillment = db.query(OSFulfillment).filter_by(id=session.fulfillment_id).first()
                if fulfillment and status in {"failed", "expired", "cancelled"}:
                    fulfillment.status = "failed"
                    fulfillment.failure_code = "PAYMENT_FAILED"
                    fulfillment.failure_message = f"공급처 결제 상태: {status}"
                db.commit()
                stats["failed"] += 1
            else:
                session.status = status if status in {"awaiting_user", "authorizing"} else session.status
                session.user_action_required = session.status == "awaiting_user"
                db.commit()
                stats["waiting"] += 1
            stats["details"].append({"payment_session_id": session_id, "status": session.status})
    return stats


def list_payment_sessions(limit: int = 200) -> list[dict[str, Any]]:
    ensure_os_schema()
    with get_db() as db:
        rows = db.query(OSPaymentSession).order_by(OSPaymentSession.id.desc()).limit(max(1, int(limit))).all()
        return [
            {
                "id": x.id,
                "fulfillment_id": x.fulfillment_id,
                "supplier": x.supplier_code,
                "mode": x.payment_mode,
                "status": x.status,
                "expected_amount_krw": x.expected_amount_krw,
                "actual_amount_krw": x.actual_amount_krw,
                "payment_url": x.payment_url,
                "user_action_required": x.user_action_required,
                "error": x.last_error,
                "updated_at": x.updated_at,
            }
            for x in rows
        ]
