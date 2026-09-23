from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict
from typing import Any

from sqlalchemy import desc, func

from app.db import Order, PlatformOrder, Product, get_db
from app.pricing.models import (
    PriceChangeBatch,
    PriceChangeBatchItem,
    PriceChangeLog,
    PriceRollbackLog,
    ensure_pricing_schema,
)
from app.sqlite_runtime import retry_sqlite_write


DEFAULT_UP_THRESHOLD_PCT = 20.0
DEFAULT_DOWN_THRESHOLD_PCT = 10.0
DEFAULT_SALES_SENSITIVE_PCT = 5.0


@dataclass
class ChangePreviewItem:
    listing_id: int
    product_id: int
    platform: str
    platform_id: str
    name: str
    before_price: float
    after_price: float
    delta: float
    change_pct: float
    sales_count: int
    guard_level: str
    guard_reason: str
    eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sales_count(product_id: int, platform: str) -> int:
    with get_db() as db:
        legacy_count = (
            db.query(func.count(Order.id))
            .filter(
                Order.product_id == product_id,
                Order.platform == platform,
                ~Order.status.in_(["cancelled", "returned"]),
            )
            .scalar()
            or 0
        )
        platform_count = (
            db.query(func.count(PlatformOrder.id))
            .filter(
                PlatformOrder.product_id == product_id,
                PlatformOrder.platform == platform,
                PlatformOrder.status != "cancelled",
            )
            .scalar()
            or 0
        )
    # 두 주문 테이블이 같은 주문을 함께 보관할 수 있어 중복 합산하지 않는다.
    return int(max(legacy_count, platform_count))


def classify_change_guard(
    *,
    current_price: float,
    target_price: float,
    eligible: bool,
    sales_count: int = 0,
    up_threshold_pct: float = DEFAULT_UP_THRESHOLD_PCT,
    down_threshold_pct: float = DEFAULT_DOWN_THRESHOLD_PCT,
    sales_sensitive_pct: float = DEFAULT_SALES_SENSITIVE_PCT,
) -> tuple[str, str, float]:
    current = float(current_price or 0)
    target = float(target_price or 0)
    if not eligible or current <= 0 or target <= 0:
        return "BLOCKED", "가격 변경 안전조건 미충족", 0.0

    change_pct = ((target - current) / current) * 100.0
    reasons: list[str] = []

    if change_pct >= abs(float(up_threshold_pct)):
        reasons.append(f"{change_pct:.1f}% 대폭 인상")
    if change_pct <= -abs(float(down_threshold_pct)):
        reasons.append(f"{abs(change_pct):.1f}% 대폭 인하")
    if sales_count > 0 and abs(change_pct) >= abs(float(sales_sensitive_pct)):
        reasons.append(f"판매이력 {sales_count}건 상품의 {abs(change_pct):.1f}% 변경")

    if reasons:
        return "SENSITIVE", " · ".join(reasons), change_pct
    if abs(target - current) < 1:
        return "UNCHANGED", "가격 변경 없음", change_pct
    return "NORMAL", "일반 변경", change_pct


def preview_price_changes(rows: list[Any]) -> dict[str, Any]:
    items: list[ChangePreviewItem] = []
    for row in rows:
        sales_count = _sales_count(int(row.product_id), str(row.platform))
        level, reason, pct = classify_change_guard(
            current_price=float(row.current_price or 0),
            target_price=float(row.target_price or 0),
            eligible=bool(row.eligible),
            sales_count=sales_count,
        )
        items.append(
            ChangePreviewItem(
                listing_id=int(row.listing_id),
                product_id=int(row.product_id),
                platform=str(row.platform),
                platform_id=str(row.platform_id),
                name=str(row.name),
                before_price=float(row.current_price or 0),
                after_price=float(row.target_price or 0),
                delta=float(row.target_price or 0) - float(row.current_price or 0),
                change_pct=pct,
                sales_count=sales_count,
                guard_level=level,
                guard_reason=reason,
                eligible=bool(row.eligible),
            )
        )

    summary = {
        "total": len(items),
        "increase": sum(1 for x in items if x.delta > 0),
        "decrease": sum(1 for x in items if x.delta < 0),
        "unchanged": sum(1 for x in items if x.guard_level == "UNCHANGED"),
        "sensitive": sum(1 for x in items if x.guard_level == "SENSITIVE"),
        "blocked": sum(1 for x in items if x.guard_level == "BLOCKED"),
        "sales_history": sum(1 for x in items if x.sales_count > 0),
        "max_increase_pct": max((x.change_pct for x in items), default=0.0),
        "max_decrease_pct": min((x.change_pct for x in items), default=0.0),
    }
    return {
        "summary": summary,
        "items": [x.to_dict() for x in items],
        "requires_extra_confirmation": summary["sensitive"] > 0,
    }


def _create_batch(preview: dict[str, Any], mode: str) -> str:
    ensure_pricing_schema()
    batch_key = uuid.uuid4().hex
    summary = preview["summary"]

    def _write() -> None:
        with get_db() as db:
            db.add(
                PriceChangeBatch(
                    batch_key=batch_key,
                    mode=str(mode or "selected")[:30],
                    total_count=int(summary["total"]),
                    sensitive_count=int(summary["sensitive"]),
                    status="running",
                )
            )
            for item in preview["items"]:
                db.add(
                    PriceChangeBatchItem(
                        batch_key=batch_key,
                        product_id=int(item["product_id"]),
                        listing_id=int(item["listing_id"]),
                        platform=str(item["platform"]),
                        platform_id=str(item["platform_id"]),
                        before_price=float(item["before_price"]),
                        after_price=float(item["after_price"]),
                        change_pct=float(item["change_pct"]),
                        sales_count=int(item["sales_count"]),
                        guard_level=str(item["guard_level"]),
                        guard_reason=str(item["guard_reason"])[:500],
                        status="blocked" if item["guard_level"] == "BLOCKED" else "pending",
                        error=str(item["guard_reason"])[:1000] if item["guard_level"] == "BLOCKED" else "",
                    )
                )
            db.commit()

    retry_sqlite_write(_write, attempts=8)
    return batch_key


def _update_batch_item(
    batch_key: str,
    listing_id: int,
    *,
    status: str,
    change_log_id: int | None = None,
    error: str = "",
) -> None:
    def _write() -> None:
        with get_db() as db:
            item = (
                db.query(PriceChangeBatchItem)
                .filter_by(batch_key=batch_key, listing_id=int(listing_id))
                .first()
            )
            if item:
                item.status = status
                item.price_change_log_id = change_log_id
                item.error = str(error or "")[:1000]
                db.add(item)
            db.commit()

    retry_sqlite_write(_write, attempts=8)


def _finish_batch(batch_key: str, success: int, failed: int) -> None:
    from datetime import datetime

    def _write() -> None:
        with get_db() as db:
            batch = db.query(PriceChangeBatch).filter_by(batch_key=batch_key).first()
            if batch:
                batch.success_count = int(success)
                batch.failed_count = int(failed)
                batch.status = "completed" if failed == 0 else "partial"
                batch.finished_at = datetime.utcnow()
                db.add(batch)
            db.commit()

    retry_sqlite_write(_write, attempts=8)


def apply_guarded_batch(
    rows: list[Any],
    *,
    mode: str = "selected",
    allow_sensitive: bool = False,
) -> dict[str, Any]:
    from app.pricing.service import apply_price

    preview = preview_price_changes(rows)
    if preview["requires_extra_confirmation"] and not allow_sensitive:
        return {
            "ok": False,
            "needs_confirmation": True,
            "preview": preview,
            "error": "급격한 가격변동 또는 판매이력 상품이 포함되어 추가 승인이 필요합니다.",
        }

    batch_key = _create_batch(preview, mode)
    item_meta = {int(x["listing_id"]): x for x in preview["items"]}
    success = failed = blocked = 0
    results: list[dict[str, Any]] = []

    for row in rows:
        meta = item_meta[int(row.listing_id)]
        if meta["guard_level"] == "BLOCKED":
            blocked += 1
            results.append({
                "ok": False,
                "listing_id": row.listing_id,
                "error": meta["guard_reason"],
                "blocked": True,
            })
            continue
        if meta["guard_level"] == "UNCHANGED":
            _update_batch_item(batch_key, row.listing_id, status="unchanged")
            results.append({
                "ok": True,
                "listing_id": row.listing_id,
                "unchanged": True,
                "price": row.current_price,
            })
            continue

        result = apply_price(row)
        results.append(result)
        if result.get("ok"):
            success += 1
            _update_batch_item(
                batch_key,
                row.listing_id,
                status="success",
                change_log_id=result.get("change_log_id"),
            )
        else:
            failed += 1
            _update_batch_item(
                batch_key,
                row.listing_id,
                status="failed",
                change_log_id=result.get("change_log_id"),
                error=str(result.get("error") or ""),
            )

    _finish_batch(batch_key, success, failed + blocked)
    return {
        "ok": failed == 0 and blocked == 0,
        "batch_key": batch_key,
        "total": len(rows),
        "success": success,
        "failed": failed,
        "blocked": blocked,
        "results": results,
        "preview": preview,
    }


def _remote_current_price(platform: str, platform_id: str) -> dict[str, Any]:
    if platform == "coupang":
        from app.platforms.coupang import get_coupang_uploader
        return get_coupang_uploader().get_current_price(platform_id)
    if platform == "smartstore":
        from app.platforms.smartstore import get_smartstore_uploader
        return get_smartstore_uploader().get_current_price(platform_id)
    return {"ok": False, "error": "지원하지 않는 판매처"}


def _remote_update_price(platform: str, platform_id: str, price: int) -> dict[str, Any]:
    if platform == "coupang":
        from app.platforms.coupang import get_coupang_uploader
        return get_coupang_uploader().update_price(platform_id, price)
    if platform == "smartstore":
        from app.platforms.smartstore import get_smartstore_uploader
        return get_smartstore_uploader().update_price(platform_id, price)
    return {"ok": False, "error": "지원하지 않는 판매처"}


def _record_rollback(
    source: PriceChangeLog,
    *,
    source_batch_key: str,
    status: str,
    error: str = "",
) -> int:
    def _write() -> int:
        with get_db() as db:
            log = PriceRollbackLog(
                source_change_log_id=int(source.id),
                source_batch_key=source_batch_key,
                product_id=int(source.product_id),
                listing_id=int(source.listing_id),
                platform=str(source.platform),
                platform_id=str(source.platform_id),
                from_price=float(source.after_price or 0),
                restored_price=float(source.before_price or 0),
                status=status,
                error=str(error or "")[:1000],
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return int(log.id)

    return retry_sqlite_write(_write, attempts=8)


def rollback_change(change_log_id: int) -> dict[str, Any]:
    ensure_pricing_schema()
    with get_db() as db:
        source = db.get(PriceChangeLog, int(change_log_id))
        if source is None:
            return {"ok": False, "error": "가격 변경 로그를 찾지 못했습니다."}
        if source.status != "success":
            return {"ok": False, "error": "성공한 가격 변경만 롤백할 수 있습니다."}

        prior_success = (
            db.query(PriceRollbackLog)
            .filter_by(source_change_log_id=source.id, status="success")
            .first()
        )
        if prior_success:
            return {"ok": False, "error": "이미 성공적으로 롤백된 가격 변경입니다."}

        batch_item = (
            db.query(PriceChangeBatchItem)
            .filter_by(price_change_log_id=source.id)
            .order_by(desc(PriceChangeBatchItem.id))
            .first()
        )
        batch_key = batch_item.batch_key if batch_item else ""

        snapshot = {
            "id": int(source.id),
            "product_id": int(source.product_id),
            "listing_id": int(source.listing_id),
            "platform": str(source.platform),
            "platform_id": str(source.platform_id),
            "before_price": float(source.before_price or 0),
            "after_price": float(source.after_price or 0),
            "batch_key": batch_key,
        }

    live = _remote_current_price(snapshot["platform"], snapshot["platform_id"])
    if not live.get("ok"):
        error = f"롤백 전 현재가 확인 실패: {live.get('error') or '알 수 없는 오류'}"
        with get_db() as db:
            source = db.get(PriceChangeLog, snapshot["id"])
            rollback_id = _record_rollback(source, source_batch_key=snapshot["batch_key"], status="failed", error=error)
        return {"ok": False, "error": error, "rollback_id": rollback_id}

    live_price = float(live.get("price") or 0)
    if abs(live_price - snapshot["after_price"]) >= 1:
        error = (
            f"현재 판매가({live_price:,.0f}원)가 이 변경의 변경후 가격"
            f"({snapshot['after_price']:,.0f}원)과 달라 자동 롤백을 차단했습니다."
        )
        with get_db() as db:
            source = db.get(PriceChangeLog, snapshot["id"])
            rollback_id = _record_rollback(source, source_batch_key=snapshot["batch_key"], status="blocked", error=error)
        return {
            "ok": False,
            "blocked": True,
            "error": error,
            "rollback_id": rollback_id,
            "live_price": live_price,
        }

    # Remote mutation is intentionally called exactly once after the drift check.
    result = _remote_update_price(
        snapshot["platform"],
        snapshot["platform_id"],
        int(snapshot["before_price"]),
    )

    with get_db() as db:
        source = db.get(PriceChangeLog, snapshot["id"])
        if result.get("ok"):
            rollback_id = _record_rollback(
                source,
                source_batch_key=snapshot["batch_key"],
                status="success",
            )
            return {
                "ok": True,
                "rollback_id": rollback_id,
                "restored_price": snapshot["before_price"],
                "change_log_id": snapshot["id"],
            }
        error = str(result.get("error") or "롤백 가격 수정 실패")
        rollback_id = _record_rollback(
            source,
            source_batch_key=snapshot["batch_key"],
            status="failed",
            error=error,
        )
        return {"ok": False, "error": error, "rollback_id": rollback_id}


def rollback_batch(batch_key: str) -> dict[str, Any]:
    ensure_pricing_schema()
    with get_db() as db:
        change_ids = [
            int(x.price_change_log_id)
            for x in (
                db.query(PriceChangeBatchItem)
                .filter(
                    PriceChangeBatchItem.batch_key == str(batch_key),
                    PriceChangeBatchItem.status == "success",
                    PriceChangeBatchItem.price_change_log_id.isnot(None),
                )
                .order_by(PriceChangeBatchItem.id.desc())
                .all()
            )
        ]

    results = [rollback_change(change_id) for change_id in change_ids]
    return {
        "batch_key": batch_key,
        "total": len(results),
        "success": sum(1 for x in results if x.get("ok")),
        "failed": sum(1 for x in results if not x.get("ok")),
        "results": results,
    }


def batch_history(limit: int = 50) -> list[dict[str, Any]]:
    ensure_pricing_schema()
    with get_db() as db:
        rows = db.query(PriceChangeBatch).order_by(desc(PriceChangeBatch.created_at)).limit(limit).all()
        return [
            {
                "배치ID": x.batch_key,
                "시각": x.created_at,
                "모드": x.mode,
                "대상": x.total_count,
                "민감변경": x.sensitive_count,
                "성공": x.success_count,
                "실패/차단": x.failed_count,
                "상태": x.status,
            }
            for x in rows
        ]


def rollback_candidates(limit: int = 100) -> list[dict[str, Any]]:
    ensure_pricing_schema()
    with get_db() as db:
        logs = (
            db.query(PriceChangeLog, Product)
            .join(Product, Product.id == PriceChangeLog.product_id)
            .filter(PriceChangeLog.status == "success")
            .order_by(PriceChangeLog.created_at.desc())
            .limit(limit * 2)
            .all()
        )
        result: list[dict[str, Any]] = []
        for log, product in logs:
            done = (
                db.query(PriceRollbackLog.id)
                .filter_by(source_change_log_id=log.id, status="success")
                .first()
            )
            if done:
                continue
            batch_item = (
                db.query(PriceChangeBatchItem)
                .filter_by(price_change_log_id=log.id)
                .order_by(desc(PriceChangeBatchItem.id))
                .first()
            )
            result.append({
                "로그ID": int(log.id),
                "배치ID": batch_item.batch_key if batch_item else "",
                "시각": log.created_at,
                "판매처": log.platform,
                "상품명": product.name,
                "변경전": log.before_price,
                "변경후": log.after_price,
            })
            if len(result) >= limit:
                break
        return result


def rollback_history(limit: int = 100) -> list[dict[str, Any]]:
    ensure_pricing_schema()
    with get_db() as db:
        rows = db.query(PriceRollbackLog).order_by(desc(PriceRollbackLog.created_at)).limit(limit).all()
        return [
            {
                "롤백ID": x.id,
                "원가격변경로그": x.source_change_log_id,
                "배치ID": x.source_batch_key,
                "시각": x.created_at,
                "판매처": x.platform,
                "변경후가격": x.from_price,
                "복원가격": x.restored_price,
                "상태": x.status,
                "오류": x.error,
            }
            for x in rows
        ]
