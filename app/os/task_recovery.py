"""Recovery/reconciliation for Seller OS safe background tasks.

The DB journal and RQ can temporarily diverge after process restarts or SQLite
contention. Recovery reconciles terminal RQ state when available, preserves active
jobs, and marks genuinely missing safe jobs as ``orphaned`` rather than pretending
the underlying business operation itself failed.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable

from redis import Redis
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.config import get_settings
from app.db import get_db
from app.os.models import OSBackgroundTask
from app.os.schema import ensure_os_schema
from app.sqlite_runtime import retry_sqlite_write

SAFE_RECOVERABLE_TYPES = {
    "legacy_bridge",
    "catalog_sync",
    "order_sync",
    "data_reconcile",
    "image_repair",
}
STALE_QUEUED_MINUTES = 15
STALE_RUNNING_MINUTES = 45
ACTIVE_RQ_STATUSES = {"queued", "started", "deferred", "scheduled"}
SUCCESS_RQ_STATUSES = {"finished"}
FAILED_RQ_STATUSES = {"failed", "stopped", "canceled", "cancelled"}


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=3)


def _loads(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        return {}


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _rq_job_snapshot(redis: Redis, job_id: str) -> dict[str, Any]:
    try:
        job = Job.fetch(job_id, connection=redis)
    except NoSuchJobError:
        return {"exists": False, "status": "missing"}

    status_obj = job.get_status(refresh=True)
    status = str(getattr(status_obj, "value", status_obj)).lower()
    snapshot: dict[str, Any] = {"exists": True, "status": status}
    if status in SUCCESS_RQ_STATUSES:
        snapshot["result"] = job.result
    elif status in FAILED_RQ_STATUSES:
        snapshot["error"] = (getattr(job, "exc_info", None) or "RQ job failed")[-4000:]
    return snapshot


def _persist_reconciliation(task_id: int, status: str, *, result: Any = None, error: str = "", now: datetime) -> None:
    def operation() -> None:
        with get_db() as db:
            row = db.query(OSBackgroundTask).filter_by(id=int(task_id)).first()
            if not row:
                return
            row.status = status
            row.finished_at = now if status in {"succeeded", "failed", "orphaned", "cancelled"} else row.finished_at
            row.error = error[:4000]
            meta = _loads(row.result_json)
            meta["reconciled_at"] = now.isoformat()
            meta["reconciled_status"] = status
            if result is not None:
                meta["result"] = result
            row.result_json = _dumps(meta)
            if status == "succeeded":
                row.progress_pct = 100
            db.commit()

    retry_sqlite_write(operation, attempts=6)


def recover_stale_safe_tasks(
    redis: Redis | None = None,
    *,
    now: datetime | None = None,
    job_snapshot: Callable[[Redis, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Reconcile stale safe tasks without turning missing queue metadata into a fake business failure."""
    ensure_os_schema()
    redis = redis or _redis()
    now = now or datetime.utcnow()
    queued_before = now - timedelta(minutes=STALE_QUEUED_MINUTES)
    running_before = now - timedelta(minutes=STALE_RUNNING_MINUTES)
    snapshotter = job_snapshot or _rq_job_snapshot

    with get_db() as db:
        candidates = (
            db.query(OSBackgroundTask)
            .filter(
                OSBackgroundTask.task_type.in_(SAFE_RECOVERABLE_TYPES),
                OSBackgroundTask.status.in_(["queued", "running"]),
            )
            .order_by(OSBackgroundTask.id.asc())
            .all()
        )
        candidate_rows = [
            {
                "id": row.id,
                "status": row.status,
                "created_at": row.created_at,
                "started_at": row.started_at,
                "result_json": row.result_json,
            }
            for row in candidates
        ]

    reconciled: list[int] = []
    orphaned: list[int] = []
    kept: list[int] = []
    failed: list[int] = []

    for row in candidate_rows:
        stale = False
        if row["status"] == "queued" and row["created_at"] and row["created_at"] < queued_before:
            stale = True
        elif row["status"] == "running" and row["started_at"] and row["started_at"] < running_before:
            stale = True
        if not stale:
            continue

        meta = _loads(row["result_json"])
        job_id = str(meta.get("rq_job_id") or f"os-task-{row['id']}")
        try:
            snap = snapshotter(redis, job_id)
        except Exception:
            # Redis inspection failure is not evidence that execution vanished.
            kept.append(row["id"])
            continue

        rq_status = str(snap.get("status") or "unknown").lower()
        if snap.get("exists") and rq_status in ACTIVE_RQ_STATUSES:
            kept.append(row["id"])
            continue

        if snap.get("exists") and rq_status in SUCCESS_RQ_STATUSES:
            _persist_reconciliation(row["id"], "succeeded", result=snap.get("result"), now=now)
            reconciled.append(row["id"])
            continue

        if snap.get("exists") and rq_status in FAILED_RQ_STATUSES:
            _persist_reconciliation(
                row["id"],
                "failed",
                error=f"RQ terminal status={rq_status}: {snap.get('error') or 'job failed'}",
                now=now,
            )
            failed.append(row["id"])
            continue

        _persist_reconciliation(
            row["id"],
            "orphaned",
            error=(
                f"자동 복구: {row['status']} 상태가 장시간 지속되었으나 RQ job({job_id})을 확인할 수 없습니다. "
                "업무 실패로 단정하지 않고 orphaned로 분리했으며, 안전 동기화 작업은 다음 스케줄에서 다시 실행할 수 있습니다."
            ),
            now=now,
        )
        orphaned.append(row["id"])

    return {
        "ok": True,
        "reconciled": len(reconciled),
        "reconciled_task_ids": reconciled,
        "orphaned": len(orphaned),
        "orphaned_task_ids": orphaned,
        "failed": len(failed),
        "failed_task_ids": failed,
        "kept_active": kept,
    }
