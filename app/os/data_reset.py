"""Administrative data reset services for Seller OS.

Two deliberately different operations live here:
- clear_work_queue_errors(): clears only error-display/history fields used by
  '오늘 할 일' while preserving orders, fulfillments and products.
- reset_all_data(): destructive local reset of every application table + Redis DB.

The full reset is intentionally SQLite-only from the UI and refuses to run while
queued/running Seller OS jobs exist. The .env file and source tree are never touched.
"""
from __future__ import annotations

from typing import Any

from redis import Redis
from sqlalchemy import text

from app.config import get_settings
from app.db import _get_engine, get_db
from app.os.models import OSAuditEvent, OSBackgroundTask, OSFulfillment, OSSalesOrderItem
from app.os.schema import ensure_os_schema


FULL_RESET_CONFIRMATION = "RESET_ALL_DATA"


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=3, socket_timeout=5)


def clear_work_queue_errors(*, actor: str = "seller") -> dict[str, Any]:
    """Clear error *display/history* data without pretending business work succeeded.

    - failed/orphaned/cancelled background task journals are removed;
    - order-item exception codes are cleared but the item's exception status remains;
    - fulfillment failure code/message are cleared but failed status remains.

    This keeps the operational truth intact while allowing the operator to clear the
    error cards shown in '오늘 할 일'.
    """
    ensure_os_schema()
    with get_db() as db:
        failed_tasks = (
            db.query(OSBackgroundTask)
            .filter(OSBackgroundTask.status.in_(["failed", "orphaned", "cancelled"]))
            .all()
        )
        task_count = len(failed_tasks)
        for row in failed_tasks:
            db.delete(row)

        exception_items = (
            db.query(OSSalesOrderItem)
            .filter(OSSalesOrderItem.status == "exception", OSSalesOrderItem.exception_code != "")
            .all()
        )
        item_count = len(exception_items)
        for row in exception_items:
            row.exception_code = ""

        failed_fulfillments = (
            db.query(OSFulfillment)
            .filter(
                OSFulfillment.status == "failed",
                (OSFulfillment.failure_code != "") | (OSFulfillment.failure_message != ""),
            )
            .all()
        )
        fulfillment_count = len(failed_fulfillments)
        for row in failed_fulfillments:
            row.failure_code = ""
            row.failure_message = ""

        db.add(OSAuditEvent(
            actor=actor,
            action="work_queue.errors_cleared",
            entity_type="seller_os",
            entity_id="today_work_queue",
            data_json=(
                '{"failed_tasks":%d,"order_exceptions":%d,"fulfillment_errors":%d}'
                % (task_count, item_count, fulfillment_count)
            ),
        ))
        db.commit()

    return {
        "ok": True,
        "failed_tasks": task_count,
        "order_exceptions": item_count,
        "fulfillment_errors": fulfillment_count,
        "total": task_count + item_count + fulfillment_count,
    }


def get_full_reset_preview() -> dict[str, Any]:
    """Return counts used by the destructive-reset confirmation UI."""
    ensure_os_schema()
    engine = _get_engine()
    dialect = str(engine.dialect.name or "")
    with get_db() as db:
        active_tasks = db.query(OSBackgroundTask).filter(
            OSBackgroundTask.status.in_(["queued", "running"])
        ).count()
    table_counts: dict[str, int] = {}
    if dialect == "sqlite":
        with engine.connect() as conn:
            names = [
                str(row[0])
                for row in conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )).fetchall()
            ]
            for name in names:
                safe_name = name.replace('"', '""')
                table_counts[name] = int(conn.execute(text(f'SELECT COUNT(*) FROM "{safe_name}"')).scalar() or 0)
    return {
        "dialect": dialect,
        "active_tasks": int(active_tasks),
        "tables": table_counts,
        "rows": int(sum(table_counts.values())),
    }


def reset_all_data(*, confirmation: str, actor: str = "seller") -> dict[str, Any]:
    """Delete every local application row and flush the configured Redis DB.

    This operation keeps database schema/source/.env intact. It is intentionally
    restricted to SQLite because the UI is a local-operator maintenance facility;
    production databases should use a dedicated DBA runbook instead.
    """
    if str(confirmation or "").strip() != FULL_RESET_CONFIRMATION:
        return {"ok": False, "error": f"확인문구가 다릅니다. {FULL_RESET_CONFIRMATION} 입력이 필요합니다."}

    preview = get_full_reset_preview()
    if preview["dialect"] != "sqlite":
        return {"ok": False, "error": "UI 전체 초기화는 로컬 SQLite 환경에서만 허용됩니다."}
    if preview["active_tasks"]:
        return {
            "ok": False,
            "error": f"실행 중/대기 중 백그라운드 작업 {preview['active_tasks']}건이 있어 초기화를 중단했습니다. 작업 종료 후 다시 시도하세요.",
        }

    redis = _redis()
    # Stop the scheduler from immediately repopulating runtime rows during reset.
    redis.set("seller-os:maintenance:reset", actor or "seller", ex=120)

    engine = _get_engine()
    deleted_tables: list[str] = []
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            rows = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )).fetchall()
            for row in rows:
                name = str(row[0])
                safe_name = name.replace('"', '""')
                conn.execute(text(f'DELETE FROM "{safe_name}"'))
                deleted_tables.append(name)
            try:
                conn.execute(text("DELETE FROM sqlite_sequence"))
            except Exception:
                pass
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")

        redis.flushdb()
    except Exception:
        try:
            redis.delete("seller-os:maintenance:reset")
        except Exception:
            pass
        raise

    return {
        "ok": True,
        "deleted_tables": len(deleted_tables),
        "deleted_rows_before_reset": preview["rows"],
        "redis_flushed": True,
        "message": "모든 애플리케이션 데이터와 Redis 상태를 초기화했습니다. .env와 소스코드는 유지됩니다.",
    }
