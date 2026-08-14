"""Persistent Seller OS background task queue.

All long-running operational work goes through Redis/RQ and a DB task journal.
Streamlit/browser lifecycle is never the owner of business work.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from redis import Redis
from rq import Queue

from app.config import get_settings
from app.db import get_db
from app.os.models import OSBackgroundTask
from app.os.schema import ensure_os_schema


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
    return Queue(name, connection=_redis(), default_timeout=1800)


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
            result = collect_platform_orders(hours=hours)
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
            from app.services.image_maintenance import repair_all_product_images
            return repair_all_product_images(limit=max(1, int(payload.get("limit", 500))))
        return image_repair
    raise ValueError(f"지원하지 않는 task_type: {task_type}")


def run_task(task_id: int) -> dict[str, Any]:
    """RQ worker entrypoint. Importable by dotted path."""
    ensure_os_schema()
    with get_db() as db:
        row = db.query(OSBackgroundTask).filter_by(id=int(task_id)).first()
        if not row:
            return {"ok": False, "error": "작업 레코드 없음"}
        if row.status == "succeeded":
            return {"ok": True, "reused": True, "result": _loads(row.result_json)}
        row.status = "running"
        row.progress_pct = max(1, row.progress_pct or 0)
        row.started_at = datetime.utcnow()
        payload = _loads(row.payload_json)
        task_type = row.task_type
        db.commit()

    try:
        result = _task_callable(task_type)(payload)
    except Exception as exc:
        with get_db() as db:
            row = db.query(OSBackgroundTask).filter_by(id=int(task_id)).first()
            if row:
                row.status = "failed"
                row.error = f"{type(exc).__name__}: {exc}"
                row.finished_at = datetime.utcnow()
                db.commit()
        raise

    with get_db() as db:
        row = db.query(OSBackgroundTask).filter_by(id=int(task_id)).first()
        if row:
            row.status = "succeeded"
            row.progress_pct = 100
            row.result_json = _dumps(result)
            row.finished_at = datetime.utcnow()
            db.commit()
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
                return {"ok": True, "task_id": existing.id, "status": existing.status, "reused": True}
        row = OSBackgroundTask(
            task_key=uuid4().hex,
            task_type=task_type,
            queue_name=queue_name,
            dedupe_key=dedupe_key,
            status="queued",
            payload_json=_dumps(payload),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        task_id = row.id

    try:
        redis = _redis()
        redis.ping()
        job = _queue(queue_name).enqueue("app.os.tasks.run_task", task_id, job_id=f"os-task-{task_id}")
        return {"ok": True, "task_id": task_id, "rq_job_id": job.id, "status": "queued", "reused": False}
    except Exception as exc:
        with get_db() as db:
            row = db.query(OSBackgroundTask).filter_by(id=task_id).first()
            if row:
                row.status = "failed"
                row.error = f"Redis/RQ 연결 실패: {exc}"
                row.finished_at = datetime.utcnow()
                db.commit()
        return {"ok": False, "task_id": task_id, "status": "failed", "error": f"백그라운드 작업 큐 연결 실패: {exc}"}


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
