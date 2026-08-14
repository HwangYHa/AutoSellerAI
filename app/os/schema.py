"""Seller OS v3 schema bootstrap and structural health checks."""
from __future__ import annotations

from typing import Any

from app.db import _get_engine, get_db
from app.os import models  # noqa: F401  # register tables on shared metadata
from app.os.models import (
    OSApprovalRequest,
    OSBackgroundTask,
    OSFulfillment,
    OSListing,
    OSOperationExecution,
    OSProduct,
    OSProductVariant,
    OSSalesOrder,
    OSSalesOrderItem,
    OSSettlementLine,
    OSSupplier,
    OSSupplierOffer,
)


def ensure_os_schema() -> None:
    """Create only the canonical OS tables if missing.

    Local SQLite uses create_all for zero-friction upgrades. Production deployments
    should still run an explicit migration step before application startup.
    """
    table_names = [table for name, table in models.Base.metadata.tables.items() if name.startswith("os_")]
    models.Base.metadata.create_all(_get_engine(), tables=table_names)


def get_os_health() -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        pending_approvals = db.query(OSApprovalRequest).filter_by(status="pending").count()
        failed_operations = db.query(OSOperationExecution).filter_by(status="failed").count()
        failed_tasks = db.query(OSBackgroundTask).filter_by(status="failed").count()
        unlinked_items = db.query(OSSalesOrderItem).filter(OSSalesOrderItem.product_id.is_(None)).count()
        unfulfilled_items = (
            db.query(OSSalesOrderItem)
            .outerjoin(OSFulfillment, OSFulfillment.order_item_id == OSSalesOrderItem.id)
            .filter(
                OSSalesOrderItem.status.notin_(["cancelled", "completed"]),
                OSFulfillment.id.is_(None),
            )
            .count()
        )
        return {
            "suppliers": db.query(OSSupplier).count(),
            "products": db.query(OSProduct).count(),
            "variants": db.query(OSProductVariant).count(),
            "offers": db.query(OSSupplierOffer).count(),
            "listings": db.query(OSListing).count(),
            "orders": db.query(OSSalesOrder).count(),
            "order_items": db.query(OSSalesOrderItem).count(),
            "fulfillments": db.query(OSFulfillment).count(),
            "settlements": db.query(OSSettlementLine).count(),
            "pending_approvals": pending_approvals,
            "failed_operations": failed_operations,
            "failed_tasks": failed_tasks,
            "unlinked_order_items": unlinked_items,
            "unfulfilled_order_items": unfulfilled_items,
        }
