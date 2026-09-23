from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc

from app.db import Product, get_db
from app.pricing.models import PriceApprovalQueue, ensure_pricing_schema
from app.pricing.supply_monitor import classify_price_risk
from app.sqlite_runtime import retry_sqlite_write


SEVERITY = {"WARNING": 1, "HIGH": 2, "CRITICAL": 3}


def sync_approval_queue(rows: list[Any], target_margin_rate: float) -> dict[str, Any]:
    ensure_pricing_schema()
    risky_listing_ids: set[int] = set()
    created = updated = escalated = resolved = 0
    new_items: list[dict[str, Any]] = []

    for row in rows:
        level, reason = classify_price_risk(
            eligible=bool(row.eligible),
            supply_price=float(row.supply_price or 0),
            current_price=float(row.current_price or 0),
            margin_rate=float(row.current_margin_rate or 0),
            target_margin_rate=float(target_margin_rate or 0),
            supply_fresh=bool(getattr(row, "supply_fresh", False)),
            supply_safe=bool(getattr(row, "supply_safe", False)),
        )
        if level not in SEVERITY:
            continue
        risky_listing_ids.add(int(row.listing_id))

        def _write() -> tuple[str, int]:
            with get_db() as db:
                q = (
                    db.query(PriceApprovalQueue)
                    .filter_by(listing_id=int(row.listing_id), status="pending")
                    .order_by(desc(PriceApprovalQueue.id))
                    .first()
                )
                action = "updated"
                old_level = ""
                if q is None:
                    q = PriceApprovalQueue(
                        product_id=int(row.product_id),
                        listing_id=int(row.listing_id),
                        platform=str(row.platform),
                        platform_id=str(row.platform_id),
                        status="pending",
                        first_detected_at=datetime.utcnow(),
                    )
                    db.add(q)
                    action = "created"
                else:
                    old_level = str(q.risk_level or "")
                    q.detection_count = int(q.detection_count or 0) + 1
                q.risk_level = level
                q.reason = reason[:500]
                q.supply_price = float(row.supply_price or 0)
                q.current_price = float(row.current_price or 0)
                q.target_price = float(row.target_price or 0)
                q.fee_rate = float(row.fee_rate or 0)
                q.margin_rate = float(row.current_margin_rate or 0)
                q.last_detected_at = datetime.utcnow()
                db.commit()
                db.refresh(q)
                if action == "updated" and SEVERITY.get(level, 0) > SEVERITY.get(old_level, 0):
                    action = "escalated"
                return action, int(q.id)

        action, queue_id = retry_sqlite_write(_write, attempts=8)
        if action == "created":
            created += 1
            new_items.append({"id": queue_id, "name": row.name, "level": level, "reason": reason})
        elif action == "escalated":
            escalated += 1
            new_items.append({"id": queue_id, "name": row.name, "level": level, "reason": reason})
        else:
            updated += 1

    def _resolve_stale_pending() -> int:
        with get_db() as db:
            rows_pending = db.query(PriceApprovalQueue).filter_by(status="pending").all()
            count = 0
            now = datetime.utcnow()
            for q in rows_pending:
                if int(q.listing_id) not in risky_listing_ids:
                    q.status = "resolved"
                    q.reviewed_at = now
                    count += 1
            if count:
                db.commit()
            return count

    resolved = retry_sqlite_write(_resolve_stale_pending, attempts=8)
    return {
        "created": created,
        "updated": updated,
        "escalated": escalated,
        "resolved": resolved,
        "pending": len(risky_listing_ids),
        "notify_items": new_items[:20],
    }


def list_approval_queue(status: str = "pending", limit: int = 500) -> list[dict[str, Any]]:
    ensure_pricing_schema()
    with get_db() as db:
        q = db.query(PriceApprovalQueue, Product).join(Product, Product.id == PriceApprovalQueue.product_id)
        if status:
            q = q.filter(PriceApprovalQueue.status == status)
        rows = q.order_by(
            desc(PriceApprovalQueue.risk_level),
            desc(PriceApprovalQueue.last_detected_at),
        ).limit(limit).all()
        return [{
            "대기ID": x.id,
            "listing_id": x.listing_id,
            "상품ID": x.product_id,
            "판매처": x.platform,
            "상품명": p.name,
            "위험": x.risk_level,
            "사유": x.reason,
            "도매가": x.supply_price,
            "현재가": x.current_price,
            "권장가": x.target_price,
            "현재마진(%)": round(float(x.margin_rate or 0) * 100, 2),
            "감지횟수": x.detection_count,
            "최초감지": x.first_detected_at,
            "최근감지": x.last_detected_at,
            "상태": x.status,
        } for x, p in rows]


def dismiss_approval(queue_id: int) -> bool:
    def _write() -> bool:
        with get_db() as db:
            q = db.get(PriceApprovalQueue, int(queue_id))
            if not q or q.status != "pending":
                return False
            q.status = "dismissed"
            q.reviewed_at = datetime.utcnow()
            db.commit()
            return True
    return retry_sqlite_write(_write, attempts=8)


def mark_approval_queue_applied(listing_id: int, change_log_id: int | None = None) -> int:
    def _write() -> int:
        with get_db() as db:
            rows = db.query(PriceApprovalQueue).filter_by(listing_id=int(listing_id), status="pending").all()
            now = datetime.utcnow()
            for q in rows:
                q.status = "applied"
                q.reviewed_at = now
                q.applied_change_log_id = int(change_log_id) if change_log_id else None
            if rows:
                db.commit()
            return len(rows)
    return retry_sqlite_write(_write, attempts=8)
