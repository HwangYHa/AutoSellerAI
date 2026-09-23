from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import desc

from app.db import get_db
from app.pricing.models import PriceApprovalQueue, PriceMonitorRun, SupplyPriceSnapshot, ensure_pricing_schema
from app.pricing.service import get_policy, load_price_rows
from app.pricing.supply_monitor import classify_price_risk, persist_price_risks, rebuild_supplier_mappings, refresh_supplier_prices
from app.sqlite_runtime import retry_sqlite_write

QUEUE_RISK_LEVELS = {"CRITICAL", "HIGH", "WARNING"}
SUPPLY_CHANGE_ALERT_RATE = 0.10


def _latest_supply_change(product_id: int) -> float:
    with get_db() as db:
        row = (
            db.query(SupplyPriceSnapshot)
            .filter(SupplyPriceSnapshot.product_id == product_id, SupplyPriceSnapshot.status == "changed")
            .order_by(desc(SupplyPriceSnapshot.checked_at))
            .first()
        )
        return float(row.change_rate or 0) if row else 0.0


def _upsert_queue_item(row: Any, *, run_key: str, risk_level: str, reason: str, supply_change_rate: float, target_margin_rate: float) -> bool:
    def _write() -> bool:
        with get_db() as db:
            existing = (
                db.query(PriceApprovalQueue)
                .filter(
                    PriceApprovalQueue.listing_id == int(row.listing_id),
                    PriceApprovalQueue.status.in_(["PENDING", "APPROVED"]),
                )
                .order_by(desc(PriceApprovalQueue.updated_at))
                .first()
            )
            created = existing is None
            item = existing or PriceApprovalQueue(
                product_id=int(row.product_id),
                listing_id=int(row.listing_id),
                platform=str(row.platform),
                platform_id=str(row.platform_id),
                product_name=str(row.name),
            )
            item.product_name = str(row.name)
            item.supply_price = float(row.supply_price or 0)
            item.current_price = float(row.current_price or 0)
            item.target_price = float(row.target_price or 0)
            item.fee_rate = float(row.fee_rate or 0)
            item.current_margin_rate = float(row.current_margin_rate or 0)
            item.target_margin_rate = float(target_margin_rate or 0)
            item.supply_change_rate = float(supply_change_rate or 0)
            item.risk_level = str(risk_level)
            item.reason = str(reason)[:500]
            item.monitor_run_key = str(run_key)
            item.last_error = ""
            db.add(item)
            db.commit()
            return created
    return retry_sqlite_write(_write, attempts=8)


def _finish_run(run_key: str, **values: Any) -> None:
    def _write() -> None:
        with get_db() as db:
            run = db.query(PriceMonitorRun).filter_by(run_key=run_key).first()
            if run:
                for key, value in values.items():
                    setattr(run, key, value)
                run.finished_at = datetime.utcnow()
                db.add(run)
            db.commit()
    retry_sqlite_write(_write, attempts=8)


def run_price_guard_monitor(*, refresh_supplier_limit: int = 500, live_market_prices: bool = True) -> dict[str, Any]:
    """Refresh cost data, scan margin risk, and enqueue approvals. Never mutates marketplace prices."""
    ensure_pricing_schema()
    run_key = uuid.uuid4().hex

    def _start() -> None:
        with get_db() as db:
            db.add(PriceMonitorRun(run_key=run_key, status="running"))
            db.commit()
    retry_sqlite_write(_start, attempts=8)

    try:
        mapping = rebuild_supplier_mappings()
        supplier = refresh_supplier_prices(max_items=int(refresh_supplier_limit))
        rows = load_price_rows(live=bool(live_market_prices))
        policy = get_policy()
        risk_counts = persist_price_risks(rows, policy.target_margin_rate)

        queued = created = 0
        critical = warning = blocked = 0
        supplier_changed = 0
        highlights: list[dict[str, Any]] = []

        for row in rows:
            risk_level, reason = classify_price_risk(
                eligible=bool(row.eligible),
                supply_price=float(row.supply_price or 0),
                current_price=float(row.current_price or 0),
                margin_rate=float(row.current_margin_rate or 0),
                target_margin_rate=float(policy.target_margin_rate or 0),
                supply_fresh=bool(row.supply_fresh),
                supply_safe=bool(row.supply_safe),
            )
            change_rate = _latest_supply_change(int(row.product_id))
            if change_rate >= SUPPLY_CHANGE_ALERT_RATE:
                supplier_changed += 1

            should_queue = risk_level in QUEUE_RISK_LEVELS or change_rate >= SUPPLY_CHANGE_ALERT_RATE
            if risk_level == "CRITICAL":
                critical += 1
            if risk_level in {"HIGH", "WARNING"}:
                warning += 1
            if risk_level == "BLOCKED":
                blocked += 1

            if not should_queue:
                continue

            combined_reason = reason
            if change_rate >= SUPPLY_CHANGE_ALERT_RATE:
                combined_reason += f" · 도매가 {change_rate:.1%} 상승"

            was_created = _upsert_queue_item(
                row,
                run_key=run_key,
                risk_level=risk_level if risk_level in QUEUE_RISK_LEVELS else "SUPPLY_UP",
                reason=combined_reason,
                supply_change_rate=change_rate,
                target_margin_rate=policy.target_margin_rate,
            )
            queued += 1
            created += 1 if was_created else 0
            highlights.append({
                "name": row.name,
                "platform": row.platform,
                "risk_level": risk_level,
                "margin": row.current_margin_rate,
                "supply_change_rate": change_rate,
                "current_price": row.current_price,
                "target_price": row.target_price,
            })

        result = {
            "run_key": run_key,
            "checked": len(rows),
            "queued": queued,
            "new_queue_items": created,
            "critical": critical,
            "warning": warning,
            "blocked": blocked,
            "supplier_changed": supplier_changed,
            "mapping": mapping,
            "supplier_refresh": supplier,
            "risk_counts": risk_counts,
            "highlights": highlights[:10],
        }
        _finish_run(
            run_key,
            checked_count=len(rows),
            queued_count=queued,
            critical_count=critical,
            warning_count=warning,
            blocked_count=blocked,
            supplier_changed_count=supplier_changed,
            status="ok",
            error="",
        )
        return result
    except Exception as exc:
        _finish_run(run_key, status="failed", error=str(exc)[:1000])
        raise


def approval_queue(status: str = "PENDING", limit: int = 500) -> list[dict[str, Any]]:
    ensure_pricing_schema()
    with get_db() as db:
        q = db.query(PriceApprovalQueue)
        if status and status != "ALL":
            q = q.filter(PriceApprovalQueue.status == status)
        rows = q.order_by(desc(PriceApprovalQueue.updated_at)).limit(limit).all()
        return [{
            "id": x.id,
            "상태": x.status,
            "위험": x.risk_level,
            "판매처": x.platform,
            "상품명": x.product_name,
            "현재가": x.current_price,
            "권장가": x.target_price,
            "현재마진(%)": round(x.current_margin_rate * 100, 2),
            "목표마진(%)": round(x.target_margin_rate * 100, 2),
            "도매가변동(%)": round(x.supply_change_rate * 100, 2),
            "사유": x.reason,
            "갱신시각": x.updated_at,
        } for x in rows]


def set_queue_status(ids: list[int], status: str) -> dict[str, int]:
    status = str(status).upper()
    if status not in {"PENDING", "APPROVED", "REJECTED"}:
        raise ValueError("지원하지 않는 승인 상태입니다.")
    now = datetime.utcnow()

    def _write() -> int:
        with get_db() as db:
            rows = db.query(PriceApprovalQueue).filter(PriceApprovalQueue.id.in_([int(x) for x in ids])).all()
            count = 0
            for row in rows:
                row.status = status
                if status == "APPROVED":
                    row.approved_at = now
                    row.rejected_at = None
                elif status == "REJECTED":
                    row.rejected_at = now
                db.add(row)
                count += 1
            db.commit()
            return count
    return {"updated": retry_sqlite_write(_write, attempts=8)}


def apply_approved_queue(ids: list[int], *, allow_sensitive: bool = False) -> dict[str, Any]:
    """Apply only explicitly approved queue items after re-fetching current marketplace prices."""
    from app.pricing.change_control import apply_guarded_batch

    ensure_pricing_schema()
    with get_db() as db:
        queued = db.query(PriceApprovalQueue).filter(
            PriceApprovalQueue.id.in_([int(x) for x in ids]),
            PriceApprovalQueue.status == "APPROVED",
        ).all()
        listing_ids = {int(x.listing_id) for x in queued}

    if not listing_ids:
        return {"ok": False, "error": "적용할 APPROVED 항목이 없습니다.", "success": 0, "failed": 0}

    live_rows = load_price_rows(live=True)
    selected = [row for row in live_rows if int(row.listing_id) in listing_ids]
    by_listing = {int(row.listing_id): row for row in selected}

    # Approved queue is never trusted as a stale price snapshot; rows are revalidated live.
    result = apply_guarded_batch(selected, mode="approval_queue", allow_sensitive=allow_sensitive)
    if result.get("needs_confirmation"):
        return result

    success_ids: list[int] = []
    failed_ids: list[int] = []
    result_by_listing = {int(x.get("listing_id")): x for x in result.get("results", []) if x.get("listing_id") is not None}

    for item in queued:
        r = result_by_listing.get(int(item.listing_id))
        if r and r.get("ok"):
            success_ids.append(int(item.id))
        else:
            failed_ids.append(int(item.id))

    def _write_result() -> None:
        with get_db() as db:
            for item_id in success_ids:
                row = db.get(PriceApprovalQueue, item_id)
                if row:
                    row.status = "APPLIED"
                    row.applied_at = datetime.utcnow()
                    row.last_error = ""
            for item_id in failed_ids:
                row = db.get(PriceApprovalQueue, item_id)
                if row:
                    row.status = "APPLY_FAILED"
                    row.last_error = str(result_by_listing.get(int(row.listing_id), {}).get("error") or "적용 실패")[:1000]
            db.commit()
    retry_sqlite_write(_write_result, attempts=8)

    return {**result, "queue_applied": len(success_ids), "queue_failed": len(failed_ids)}


def monitor_history(limit: int = 50) -> list[dict[str, Any]]:
    ensure_pricing_schema()
    with get_db() as db:
        rows = db.query(PriceMonitorRun).order_by(desc(PriceMonitorRun.started_at)).limit(limit).all()
        return [{
            "실행시각": x.started_at,
            "상태": x.status,
            "점검": x.checked_count,
            "대기열": x.queued_count,
            "긴급": x.critical_count,
            "경고": x.warning_count,
            "차단": x.blocked_count,
            "도매가상승": x.supplier_changed_count,
            "오류": x.error,
        } for x in rows]
