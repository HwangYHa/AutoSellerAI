"""재고 사입 발주 안전장치.

AutoSellerAI의 기본 사업모델은 위탁판매이므로 PurchaseOrder(재고 사입)는 기본 OFF다.
판매채널 주문 → 공급처 개별발주와 재고 사입을 분리해 오조작을 막는다.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from app.db import Inventory, PurchaseOrder, PurchaseOrderItem, get_db, init_db, _get_engine


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def inventory_replenishment_enabled() -> bool:
    return _truthy(os.getenv("INVENTORY_REPLENISHMENT_ENABLED", "false"))


def ensure_procurement_guard() -> dict[str, Any]:
    """재고 사입이 OFF면 SQLite trigger로 PurchaseOrder 신규 생성을 차단한다.

    기존 주문/플랫폼 위탁발주에는 영향이 없다.
    """
    init_db()
    enabled = inventory_replenishment_enabled()
    engine = _get_engine()
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TRIGGER IF EXISTS guard_purchase_orders_disabled")
        if not enabled:
            conn.exec_driver_sql(
                """
                CREATE TRIGGER guard_purchase_orders_disabled
                BEFORE INSERT ON purchase_orders
                BEGIN
                    SELECT RAISE(ABORT, '재고 사입 발주가 비활성화되어 있습니다. 위탁판매 주문 발주와 혼동하지 마세요.');
                END;
                """
            )
    return {"inventory_replenishment_enabled": enabled, "guard_active": not enabled}


def cancel_latest_local_purchase_order(max_age_minutes: int = 180) -> dict[str, Any]:
    """최근 생성된 draft/confirmed 재고 사입 발주서 1건을 취소한다.

    외부 공급처 API를 호출하지 않는다. PurchaseOrder가 애초에 로컬 재고 사입용이기 때문이다.
    qty_incoming도 함께 원복한다.
    """
    init_db()
    cutoff = datetime.utcnow() - timedelta(minutes=max(1, int(max_age_minutes)))
    with get_db() as db:
        po = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.status.in_(["draft", "confirmed"]),
                PurchaseOrder.created_at >= cutoff,
            )
            .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
            .first()
        )
        if not po:
            return {
                "ok": False,
                "error": f"최근 {max_age_minutes}분 내 취소 가능한 로컬 재고 발주서가 없습니다.",
            }

        items = db.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
        for item in items:
            inv = db.query(Inventory).filter_by(product_id=item.product_id).first()
            if inv:
                inv.qty_incoming = max(0, int(inv.qty_incoming or 0) - int(item.quantity or 0))

        old_status = po.status
        po.status = "cancelled"
        stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        note = f"긴급취소 {stamp}"
        po.memo = f"{po.memo} | {note}".strip(" |")
        db.commit()

        return {
            "ok": True,
            "po_id": po.id,
            "po_number": po.po_number,
            "previous_status": old_status,
            "status": "cancelled",
            "total_amount": float(po.total_amount or 0),
            "item_count": len(items),
            "created_at": po.created_at.isoformat() if po.created_at else "",
            "external_order_sent": False,
        }


def get_recent_local_purchase_orders(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with get_db() as db:
        rows = db.query(PurchaseOrder).order_by(PurchaseOrder.created_at.desc()).limit(limit).all()
        result = []
        for po in rows:
            item_count = db.query(PurchaseOrderItem).filter_by(po_id=po.id).count()
            result.append({
                "id": po.id,
                "po_number": po.po_number,
                "supplier": po.supplier,
                "status": po.status,
                "total_amount": float(po.total_amount or 0),
                "item_count": item_count,
                "created_at": po.created_at.isoformat() if po.created_at else "",
            })
        return result
