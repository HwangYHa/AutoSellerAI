"""Persistent Seller OS background task queue.

The DB journal is the durable business-facing task state. Redis/RQ owns execution.
Task state writes are rebuilt/retried on transient SQLite contention so a completed
RQ job is not left permanently marked as running.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from redis import Redis
from rq import Queue, get_current_job

from app.config import get_settings
from app.db import get_db
from app.os.models import OSBackgroundTask
from app.os.schema import ensure_os_schema
from app.sqlite_runtime import retry_sqlite_write

# Long sync jobs can legitimately exceed the old 30 minute RQ default.
TASK_TIMEOUT_SECONDS: dict[str, int] = {
    "legacy_bridge": 1800,
    "catalog_sync": 3600,
    "order_sync": 5400,
    "data_reconcile": 3600,
    "image_repair": 7200,
    "listing_publish": 1800,
    "supplier_order": 1800,
}
RQ_RESULT_TTL_SECONDS = 24 * 60 * 60
RQ_FAILURE_TTL_SECONDS = 7 * 24 * 60 * 60


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        return {}


def _redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=5)


def _queue(name: str) -> Queue:
    return Queue(name, connection=_redis(), default_timeout=3600)


def _task_timeout(task_type: str) -> int:
    return int(TASK_TIMEOUT_SECONDS.get(task_type, 3600))


def _task_callable(task_type: str) -> Callable[[dict[str, Any]], Any]:
    if task_type == "legacy_bridge":
        from app.os.bridge import migrate_legacy_to_os
        return lambda payload: migrate_legacy_to_os()

    if task_type == "catalog_sync":
        def sync_catalogs(payload: dict[str, Any]) -> Any:
            from app.sync.catalog_sync import sync_coupang_catalog, sync_smartstore_catalog
            result: dict[str, Any] = {}
            requested = payload.get("platforms") or ["coupang", "smartstore"]
            if "coupang" in requested:
                result["coupang"] = sync_coupang_catalog()
            if "smartstore" in requested:
                result["smartstore"] = sync_smartstore_catalog()
            from app.os.bridge import migrate_legacy_to_os
            result["bridge"] = migrate_legacy_to_os()
            return result
        return sync_catalogs

    if task_type == "order_sync":
        def sync_orders(payload: dict[str, Any]) -> Any:
            from app.pipeline import collect_platform_orders
            hours = max(1, int(payload.get("hours", 24)))
            result = collect_platform_orders(hours_back=hours)
            from app.services.data_graph import reconcile_data_graph
            from app.os.bridge import migrate_legacy_to_os
            return {
                "orders": result,
                "legacy_graph": reconcile_data_graph(fetch_remote_identities=True),
                "bridge": migrate_legacy_to_os(),
            }
        return sync_orders

    if task_type == "data_reconcile":
        def reconcile(payload: dict[str, Any]) -> Any:
            from app.services.data_graph import reconcile_data_graph
            from app.os.bridge import migrate_legacy_to_os
            return {
                "legacy_graph": reconcile_data_graph(fetch_remote_identities=bool(payload.get("remote", False))),
                "bridge": migrate_legacy_to_os(),
            }
        return reconcile

    if task_type == "image_repair":
        def image_repair(payload: dict[str, Any]) -> Any:
            from app.services.image_maintenance import (
                refresh_supplier_images_responsive,
                repair_all_product_images_responsive,
            )
            include_marketplaces = bool(payload.get("include_marketplaces", True))
            if "limit" in payload and not include_marketplaces:
                return refresh_supplier_images_responsive(limit=max(1, int(payload.get("limit", 300))))
            return repair_all_product_images_responsive(include_marketplaces=include_marketplaces)
        return image_repair

    if task_type == "listing_publish":
        def publish_listing(payload: dict[str, Any]) -> Any:
            approval_id = int(payload.get("approval_id") or 0)
            if approval_id <= 0:
                raise ValueError("listing_publish 작업에는 approval_id가 필요합니다.")
            from app.os.operations import execute_listing_publish
            result = execute_listing_publish(approval_id, actor="worker")
            if not result.get("ok"):
                raise RuntimeError(result.get("error") or "승인된 상품등록 실행 실패")
            return result
        return publish_listing

    if task_type == "supplier_order":
        def create_supplier_order(payload: dict[str, Any]) -> Any:
            approval_id = int(payload.get("approval_id") or 0)
            if approval_id <= 0:
                raise ValueError("supplier_order 작업에는 approval_id가 필요합니다.")
            from app.os.fulfillment_executor import execute_supplier_order
            result = execute_supplier_order(approval_id, actor="worker")
            if not result.get("ok"):
                raise RuntimeError(result.get("error") or "승인된 공급처 발주 실행 실패")
            return result
        return create_supplier_order

    raise ValueError(f"지원하지 않는 task_type: {task_type}")


def _persist_state(task_id: int, updater: Callable[[OSBackgroundTask], None]) -> bool:
    """Persist one journal transition using a fresh transaction on every retry."""
    def operation() -> bool:
        ensure_os_schema()
        with get_db() as db:
            row = db.query(OSBackgroundTask).filter_by(id=int(task_id)).first()
            if not row:
                return False
            updater(row)
            db.commit()
            return True

    return retry_sqlite_write(operation, attempts=6)


def run_task(task_id: int) -> dict[str, Any]:
    """RQ worker entrypoint. Importable by dotted path."""
    ensure_os_schema()
    with get_db() as db:
        row = db.query(OSBackgroundTask).filter_by(id=int(task_id)).first()
        if not row:
            return {"ok": False, "error": "작업 레코드 없음"}
        if row.status == "succeeded":
            return {"ok": True, "reused": True, "result": _loads(row.result_json)}
        payload = _loads(row.payload_json)
        task_type = row.task_type

    job = get_current_job()
    rq_job_id = job.id if job else f"os-task-{task_id}"

    def mark_running(row: OSBackgroundTask) -> None:
        row.status = "running"
        row.progress_pct = max(1, row.progress_pct or 0)
        row.started_at = row.started_at or datetime.utcnow()
        row.finished_at = None
        row.error = ""
        meta = _loads(row.result_json)
        meta["rq_job_id"] = rq_job_id
        meta["worker_started_at"] = datetime.utcnow().isoformat()
        row.result_json = _dumps(meta)

    _persist_state(task_id, mark_running)

    try:
        result = _task_callable(task_type)(payload)
    except Exception as exc:
        def mark_failed(row: OSBackgroundTask) -> None:
            row.status = "failed"
            row.error = f"{type(exc).__name__}: {exc}"[:4000]
            row.finished_at = datetime.utcnow()
            meta = _loads(row.result_json)
            meta["rq_job_id"] = rq_job_id
            meta["worker_finished_at"] = row.finished_at.isoformat()
            row.result_json = _dumps(meta)

        _persist_state(task_id, mark_failed)
        raise

    def mark_succeeded(row: OSBackgroundTask) -> None:
        row.status = "succeeded"
        row.progress_pct = 100
        row.error = ""
        row.finished_at = datetime.utcnow()
        row.result_json = _dumps({
            "rq_job_id": rq_job_id,
            "worker_finished_at": row.finished_at.isoformat(),
            "result": result,
        })

    _persist_state(task_id, mark_succeeded)
    return {"ok": True, "result": result}


def enqueue_task(
    task_type: str,
    payload: dict[str, Any] | None = None,
    *,
    queue_name: str = "sync",
    dedupe_key: str = "",
) -> dict[str, Any]:
    ensure_os_schema()
    payload = payload or {}

    def create_journal_row() -> dict[str, Any]:
        with get_db() as db:
            if dedupe_key:
                existing = (
                    db.query(OSBackgroundTask)
                    .filter(
                        OSBackgroundTask.task_type == task_type,
                        OSBackgroundTask.dedupe_key == dedupe_key,
                        OSBackgroundTask.status.in_(["queued", "running"]),
                    )
                    .order_by(OSBackgroundTask.id.desc())
                    .first()
                )
                if existing:
                    return {"reused": True, "task_id": existing.id, "status": existing.status}
            row = OSBackgroundTask(
                task_key=uuid4().hex,
                task_type=task_type,
                queue_name=queue_name,
                dedupe_key=dedupe_key,
                status="queued",
                payload_json=_dumps(payload),
                result_json="{}",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return {"reused": False, "task_id": row.id, "status": row.status}

    journal = retry_sqlite_write(create_journal_row, attempts=6)
    task_id = int(journal["task_id"])
    if journal["reused"]:
        return {"ok": True, "task_id": task_id, "status": journal["status"], "reused": True}

    job_id = f"os-task-{task_id}"
    try:
        redis = _redis()
        redis.ping()
        job = _queue(queue_name).enqueue(
            "app.os.tasks.run_task",
            task_id,
            job_id=job_id,
            job_timeout=_task_timeout(task_type),
            result_ttl=RQ_RESULT_TTL_SECONDS,
            failure_ttl=RQ_FAILURE_TTL_SECONDS,
        )

        def mark_enqueued(row: OSBackgroundTask) -> None:
            meta = _loads(row.result_json)
            meta.update({
                "rq_job_id": job.id,
                "rq_timeout_seconds": _task_timeout(task_type),
                "rq_result_ttl_seconds": RQ_RESULT_TTL_SECONDS,
                "enqueued_at": datetime.utcnow().isoformat(),
            })
            row.result_json = _dumps(meta)

        _persist_state(task_id, mark_enqueued)
        return {"ok": True, "task_id": task_id, "rq_job_id": job.id, "status": "queued", "reused": False}
    except Exception as exc:
        def mark_enqueue_failed(row: OSBackgroundTask) -> None:
            row.status = "failed"
            row.error = f"Redis/RQ enqueue 실패: {exc}"[:4000]
            row.finished_at = datetime.utcnow()

        _persist_state(task_id, mark_enqueue_failed)
        return {
            "ok": False,
            "task_id": task_id,
            "status": "failed",
            "error": f"백그라운드 작업 큐 연결 실패: {exc}",
        }


def get_task(task_id: int | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    ensure_os_schema()
    with get_db() as db:
        row = db.query(OSBackgroundTask).filter_by(id=int(task_id)).first()
        if not row:
            return None
        return {
            "id": row.id,
            "task_type": row.task_type,
            "queue_name": row.queue_name,
            "status": row.status,
            "progress_pct": row.progress_pct,
            "result": _loads(row.result_json),
            "error": row.error,
            "created_at": row.created_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
        }


def list_tasks(limit: int = 50) -> list[dict[str, Any]]:
    ensure_os_schema()
    with get_db() as db:
        rows = db.query(OSBackgroundTask).order_by(OSBackgroundTask.id.desc()).limit(max(1, int(limit))).all()
        return [
            {
                "id": x.id,
                "type": x.task_type,
                "queue": x.queue_name,
                "status": x.status,
                "progress": x.progress_pct,
                "error": x.error,
                "created_at": x.created_at,
            }
            for x in rows
        ]
