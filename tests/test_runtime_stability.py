from datetime import datetime, timedelta
from uuid import uuid4

from app.db import get_db
from app.os.models import OSBackgroundTask
from app.os.runtime_health import _worst
from app.os.schema import ensure_os_schema
from app.os.task_recovery import recover_stale_safe_tasks


def _task(task_type: str, status: str, created_at: datetime) -> OSBackgroundTask:
    return OSBackgroundTask(
        task_key=uuid4().hex,
        task_type=task_type,
        queue_name="dangerous" if task_type == "listing_publish" else "sync",
        dedupe_key=f"test:{uuid4().hex}",
        status=status,
        payload_json="{}",
        created_at=created_at,
        started_at=created_at if status == "running" else None,
    )


def test_runtime_health_uses_worst_component_status():
    assert _worst("ok", "ok") == "ok"
    assert _worst("ok", "degraded") == "degraded"
    assert _worst("degraded", "down", "ok") == "down"


def test_recovery_marks_only_missing_safe_tasks_orphaned():
    ensure_os_schema()
    now = datetime.utcnow()
    safe = _task("order_sync", "queued", now - timedelta(minutes=30))
    dangerous = _task("listing_publish", "queued", now - timedelta(minutes=30))

    with get_db() as db:
        db.add_all([safe, dangerous])
        db.commit()
        db.refresh(safe)
        db.refresh(dangerous)
        safe_id = safe.id
        dangerous_id = dangerous.id

    try:
        result = recover_stale_safe_tasks(
            redis=object(),
            now=now,
            job_snapshot=lambda _redis, _job_id: {"exists": False, "status": "missing"},
        )
        assert safe_id in result["orphaned_task_ids"]
        assert dangerous_id not in result["orphaned_task_ids"]
        assert result["failed"] == 0

        with get_db() as db:
            safe_row = db.get(OSBackgroundTask, safe_id)
            dangerous_row = db.get(OSBackgroundTask, dangerous_id)
            assert safe_row.status == "orphaned"
            assert "자동 복구" in safe_row.error
            assert dangerous_row.status == "queued"
    finally:
        with get_db() as db:
            for task_id in (safe_id, dangerous_id):
                row = db.get(OSBackgroundTask, task_id)
                if row:
                    db.delete(row)
            db.commit()


def test_recovery_keeps_safe_task_when_rq_job_is_active():
    ensure_os_schema()
    now = datetime.utcnow()
    safe = _task("data_reconcile", "running", now - timedelta(minutes=60))

    with get_db() as db:
        db.add(safe)
        db.commit()
        db.refresh(safe)
        task_id = safe.id

    try:
        result = recover_stale_safe_tasks(
            redis=object(),
            now=now,
            job_snapshot=lambda _redis, _job_id: {"exists": True, "status": "started"},
        )
        assert result["orphaned"] == 0
        assert result["failed"] == 0
        assert task_id in result["kept_active"]
        with get_db() as db:
            assert db.get(OSBackgroundTask, task_id).status == "running"
    finally:
        with get_db() as db:
            row = db.get(OSBackgroundTask, task_id)
            if row:
                db.delete(row)
            db.commit()
