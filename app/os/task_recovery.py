"""Recovery for orphaned Seller OS safe background tasks.

Only read/sync/reconcile task types are eligible. Dangerous marketplace/supplier
mutations are deliberately excluded because recovery must never create an
implicit external retry.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from redis import Redis
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.config import get_settings
from app.db import get_db
from app.os.models import OSBackgroundTask
from app.os.schema import ensure_os_schema

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


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=3)


def _rq_job_active(redis: Redis, job_id: str) -> bool:
    try:
        job = Job.fetch(job_id, connection=redis)
    except NoSuchJobError:
        return False
    status = job.get_status(refresh=True)
    value = getattr(status, "value", status)
    return str(value).lower() in ACTIVE_RQ_STATUSES


def recover_stale_safe_tasks(
    redis: Redis | None = None,
    *,
    now: datetime | None = None,
    job_active: Callable[[Redis, str], bool] | None = None,
) -> dict[str, Any]:
    """Fail DB tasks whose RQ job disappeared after worker/Redis interruption.

    This releases stable dedupe keys so the normal scheduler can enqueue the next
    safe run. It never touches dangerous task types such as listing_publish or
    supplier_order.
    """
    ensure_os_schema()
    redis = redis or _redis()
    now = now or datetime.utcnow()
    queued_before = now - timedelta(minutes=STALE_QUEUED_MINUTES)
    running_before = now - timedelta(minutes=STALE_RUNNING_MINUTES)
    is_active = job_active or _rq_job_active

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

        recovered: list[int] = []
        kept: list[int] = []
        for row in candidates:
            stale = False
            if row.status == "queued" and row.created_at and row.created_at < queued_before:
                stale = True
            elif row.status == "running" and row.started_at and row.started_at < running_before:
                stale = True
            if not stale:
                continue

            job_id = f"os-task-{row.id}"
            try:
                active = bool(is_active(redis, job_id))
            except Exception:
                # Redis inspection failure is not evidence that the job vanished.
                kept.append(row.id)
                continue
            if active:
                kept.append(row.id)
                continue

            previous = row.status
            row.status = "failed"
            row.error = (
                f"자동 복구: {previous} 상태가 장시간 지속되었고 RQ job({job_id})이 존재하지 않습니다. "
                "안전 동기화 작업만 종료 처리했으며 다음 스케줄에서 재실행할 수 있습니다."
            )
            row.finished_at = now
            recovered.append(row.id)

        if recovered:
            db.commit()

    return {
        "ok": True,
        "recovered": len(recovered),
        "task_ids": recovered,
        "kept_active": kept,
    }
