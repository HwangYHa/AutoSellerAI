"""Seller OS read model: one work queue instead of scattered operational menus."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func

from app.db import get_db
from app.os.approvals import get_pending_approvals
from app.os.models import (
    OSBackgroundTask,
    OSFulfillment,
    OSListing,
    OSProduct,
    OSSalesOrder,
    OSSalesOrderItem,
    OSSettlementLine,
)
from app.os.schema import ensure_os_schema, get_os_health


def get_dashboard() -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        revenue = int(db.query(func.coalesce(func.sum(OSSettlementLine.gross_revenue_krw), 0)).scalar() or 0)
        profit = int(db.query(func.coalesce(func.sum(OSSettlementLine.net_profit_krw), 0)).scalar() or 0)
        return {
            "health": get_os_health(),
            "metrics": {
                "products": db.query(OSProduct).filter(OSProduct.status != "archived").count(),
                "active_listings": db.query(OSListing).filter_by(status="active").count(),
                "open_orders": db.query(OSSalesOrder).filter(
                    OSSalesOrder.status.notin_(["completed", "cancelled"])
                ).count(),
                "revenue_krw": revenue,
                "profit_krw": profit,
            },
            "work_queue": get_work_queue(limit=100),
        }


def get_work_queue(limit: int = 100) -> list[dict[str, Any]]:
    """Return only items that require a human decision or exception handling.

    Error records whose display payload has been explicitly cleared by the operator
    remain truthful in their business status, but no longer clutter '오늘 할 일'.
    """
    ensure_os_schema()
    result: list[dict[str, Any]] = []
    for approval in get_pending_approvals(limit=limit):
        result.append({
            "priority": 10 if approval["risk_level"] == "critical" else 20,
            "kind": "approval",
            "action_type": approval["action_type"],
            "id": approval["id"],
            "title": approval["summary"] or approval["action_type"],
            "detail": f"{approval['entity_type']} #{approval['entity_id']}",
            "created_at": approval["requested_at"],
            "action": "승인/거절",
        })

    with get_db() as db:
        exceptions = (
            db.query(OSSalesOrderItem)
            .filter(
                OSSalesOrderItem.status == "exception",
                OSSalesOrderItem.exception_code != "",
            )
            .order_by(OSSalesOrderItem.updated_at.asc())
            .limit(limit)
            .all()
        )
        for item in exceptions:
            result.append({
                "priority": 5,
                "kind": "order_exception",
                "action_type": "order.exception",
                "id": item.id,
                "title": item.product_name or "주문 상품 연결 필요",
                "detail": item.exception_code or "주문 예외",
                "created_at": item.updated_at,
                "action": "예외 처리",
            })

        failed_fulfillments = (
            db.query(OSFulfillment)
            .filter(
                OSFulfillment.status == "failed",
                (OSFulfillment.failure_code != "") | (OSFulfillment.failure_message != ""),
            )
            .order_by(OSFulfillment.updated_at.asc())
            .limit(limit)
            .all()
        )
        for f in failed_fulfillments:
            result.append({
                "priority": 3,
                "kind": "fulfillment_failed",
                "action_type": "supplier.order.failed",
                "id": f.id,
                "title": f"공급처 발주 실패 · {f.supplier_code or '공급처 미확인'}",
                "detail": f.failure_message or f.failure_code or "발주 실패",
                "created_at": f.updated_at,
                "action": "재검토",
            })

        failed_tasks = (
            db.query(OSBackgroundTask)
            .filter(OSBackgroundTask.status.in_(["failed", "orphaned"]))
            .order_by(OSBackgroundTask.created_at.desc())
            .limit(20)
            .all()
        )
        for task in failed_tasks:
            result.append({
                "priority": 30,
                "kind": "task_failed",
                "action_type": "automation.failed",
                "id": task.id,
                "title": f"자동화 작업 실패 · {task.task_type}",
                "detail": task.error[:240],
                "created_at": task.created_at,
                "action": "원인 확인",
            })

    def sort_key(row: dict[str, Any]):
        created = row.get("created_at") or datetime.min
        return (int(row.get("priority", 99)), created)

    return sorted(result, key=sort_key)[: max(1, int(limit))]


def list_products(*, status: str = "", keyword: str = "", limit: int = 100) -> list[dict[str, Any]]:
    ensure_os_schema()
    with get_db() as db:
        q = db.query(OSProduct)
        if status:
            q = q.filter(OSProduct.status == status)
        if keyword.strip():
            token = f"%{keyword.strip()}%"
            q = q.filter((OSProduct.name.like(token)) | (OSProduct.sku.like(token)) | (OSProduct.brand.like(token)))
        rows = q.order_by(OSProduct.updated_at.desc()).limit(max(1, int(limit))).all()
        result = []
        for p in rows:
            listings = db.query(OSListing).filter_by(product_id=p.id).all()
            result.append({
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "brand": p.brand,
                "category": p.category,
                "status": p.status,
                "type": p.product_type,
                "channels": ", ".join(sorted({x.platform for x in listings if x.status == "active"})),
                "updated_at": p.updated_at,
            })
        return result


def list_orders(*, status: str = "", limit: int = 100) -> list[dict[str, Any]]:
    ensure_os_schema()
    with get_db() as db:
        q = db.query(OSSalesOrder)
        if status:
            q = q.filter_by(status=status)
        orders = q.order_by(OSSalesOrder.ordered_at.desc()).limit(max(1, int(limit))).all()
        result = []
        for order in orders:
            items = db.query(OSSalesOrderItem).filter_by(order_id=order.id).all()
            result.append({
                "id": order.id,
                "platform": order.platform,
                "order_no": order.external_order_id,
                "status": order.status,
                "receiver": order.receiver_name,
                "items": len(items),
                "exceptions": sum(1 for x in items if x.status == "exception" and x.exception_code),
                "amount_krw": sum(int(x.unit_sale_price_krw or 0) * int(x.quantity or 0) for x in items),
                "ordered_at": order.ordered_at,
            })
        return result
