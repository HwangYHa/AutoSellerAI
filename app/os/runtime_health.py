"""Seller OS runtime readiness diagnostics.

This module is intentionally cheap and read-only. It checks the local operational
spine (DB, Redis, RQ workers/queues, task journal and critical configuration)
without performing paid AI calls or marketplace mutations.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from redis import Redis
from rq import Queue, Worker
from rq.registry import FailedJobRegistry, StartedJobRegistry
from sqlalchemy import text

from app.config import get_settings
from app.db import get_db
from app.os.models import OSBackgroundTask
from app.os.schema import ensure_os_schema

QUEUE_NAMES = ("sync", "automation", "dangerous", "threads")
QUEUE_BACKLOG_WARN = 20
QUEUE_BACKLOG_CRITICAL = 100
STALE_QUEUED_MINUTES = 15
STALE_RUNNING_MINUTES = 45


def _redis() -> Redis:
    s = get_settings()
    return Redis.from_url(s.redis_url, socket_connect_timeout=2, socket_timeout=3)


def _status_rank(status: str) -> int:
    return {"ok": 0, "degraded": 1, "down": 2}.get(status, 2)


def _worst(*statuses: str) -> str:
    return max(statuses or ("ok",), key=_status_rank)


def _database_health() -> dict[str, Any]:
    try:
        with get_db() as db:
            db.execute(text("SELECT 1"))
            journal_mode = str(db.execute(text("PRAGMA journal_mode")).scalar() or "").lower()
            busy_timeout = int(db.execute(text("PRAGMA busy_timeout")).scalar() or 0)
            synchronous = int(db.execute(text("PRAGMA synchronous")).scalar() or 0)
        s = get_settings()
        path = Path(str(s.db_path or ""))
        reasons: list[str] = []
        status = "ok"
        if journal_mode != "wal":
            status = "degraded"
            reasons.append(f"journal_mode={journal_mode or 'unknown'}")
        if busy_timeout < 30_000:
            status = "degraded"
            reasons.append(f"busy_timeout={busy_timeout}ms")
        return {
            "status": status,
            "path": str(path),
            "exists": path.exists() if str(path) else False,
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "journal_mode": journal_mode,
            "busy_timeout_ms": busy_timeout,
            "synchronous": synchronous,
            "reason": "; ".join(reasons),
        }
    except Exception as exc:
        return {"status": "down", "error": f"{type(exc).__name__}: {exc}"[:300]}


def _queue_health(redis: Redis) -> dict[str, Any]:
    workers = Worker.all(connection=redis)
    worker_queues: dict[str, int] = {name: 0 for name in QUEUE_NAMES}
    worker_names: list[str] = []
    for worker in workers:
        worker_names.append(worker.name)
        for queue in worker.queues:
            if queue.name in worker_queues:
                worker_queues[queue.name] += 1

    queues: dict[str, Any] = {}
    overall = "ok"
    for name in QUEUE_NAMES:
        q = Queue(name, connection=redis)
        queued = int(q.count)
        started = int(StartedJobRegistry(name, connection=redis).count)
        failed = int(FailedJobRegistry(name, connection=redis).count)
        worker_count = worker_queues.get(name, 0)

        status = "ok"
        reasons: list[str] = []
        if queued and worker_count == 0:
            status = "down"
            reasons.append("대기 작업이 있지만 처리 worker가 없습니다")
        elif worker_count == 0:
            status = "degraded"
            reasons.append("처리 worker가 없습니다")
        if queued >= QUEUE_BACKLOG_CRITICAL:
            status = "down"
            reasons.append(f"대기열 {queued}건")
        elif queued >= QUEUE_BACKLOG_WARN and status != "down":
            status = "degraded"
            reasons.append(f"대기열 {queued}건")
        if failed >= 10 and status == "ok":
            status = "degraded"
            reasons.append(f"RQ 실패 registry {failed}건")

        queues[name] = {
            "status": status,
            "queued": queued,
            "started": started,
            "failed_registry": failed,
            "workers": worker_count,
            "reason": "; ".join(reasons),
        }
        overall = _worst(overall, status)

    return {
        "status": overall,
        "worker_count": len(workers),
        "worker_names": worker_names,
        "queues": queues,
    }


def _task_journal_health() -> dict[str, Any]:
    ensure_os_schema()
    now = datetime.utcnow()
    queued_before = now - timedelta(minutes=STALE_QUEUED_MINUTES)
    running_before = now - timedelta(minutes=STALE_RUNNING_MINUTES)
    try:
        with get_db() as db:
            stale_queued = (
                db.query(OSBackgroundTask)
                .filter(OSBackgroundTask.status == "queued", OSBackgroundTask.created_at < queued_before)
                .count()
            )
            stale_running = (
                db.query(OSBackgroundTask)
                .filter(OSBackgroundTask.status == "running", OSBackgroundTask.started_at < running_before)
                .count()
            )
            recent_failed = (
                db.query(OSBackgroundTask)
                .filter(OSBackgroundTask.status == "failed", OSBackgroundTask.created_at >= now - timedelta(hours=24))
                .count()
            )
            recent_orphaned = (
                db.query(OSBackgroundTask)
                .filter(OSBackgroundTask.status == "orphaned", OSBackgroundTask.created_at >= now - timedelta(hours=24))
                .count()
            )
            active = (
                db.query(OSBackgroundTask)
                .filter(OSBackgroundTask.status.in_(["queued", "running"]))
                .count()
            )

        status = "ok"
        reasons: list[str] = []
        if stale_running:
            status = "down"
            reasons.append(f"{STALE_RUNNING_MINUTES}분 초과 running {stale_running}건")
        if stale_queued and status != "down":
            status = "degraded"
            reasons.append(f"{STALE_QUEUED_MINUTES}분 초과 queued {stale_queued}건")
        if recent_failed >= 5 and status == "ok":
            status = "degraded"
            reasons.append(f"24시간 실제 실패 {recent_failed}건")
        if recent_orphaned and status == "ok":
            status = "degraded"
            reasons.append(f"24시간 큐 상태 유실(orphaned) {recent_orphaned}건")

        return {
            "status": status,
            "active": active,
            "stale_queued": stale_queued,
            "stale_running": stale_running,
            "failed_24h": recent_failed,
            "orphaned_24h": recent_orphaned,
            "reason": "; ".join(reasons),
        }
    except Exception as exc:
        return {"status": "down", "error": f"{type(exc).__name__}: {exc}"[:300]}


def _configuration_health() -> dict[str, Any]:
    s = get_settings()
    naver_secret = str(s.naver_client_secret or "").strip()
    checks = {
        "coupang": bool(s.coupang_access_key and s.coupang_secret_key and s.coupang_vendor_id),
        "smartstore": bool(
            s.naver_client_id
            and len(naver_secret) == 29
            and naver_secret.startswith(("$2a$", "$2b$", "$2y$"))
        ),
        "redis": bool(s.redis_url),
    }
    missing = [name for name, ok in checks.items() if not ok]
    return {
        "status": "ok" if not missing else "degraded",
        "checks": checks,
        "missing_or_invalid": missing,
    }


def get_runtime_health() -> dict[str, Any]:
    database = _database_health()
    config = _configuration_health()

    try:
        redis = _redis()
        redis.ping()
        redis_health: dict[str, Any] = {"status": "ok"}
        queues = _queue_health(redis)
    except Exception as exc:
        redis_health = {"status": "down", "error": f"{type(exc).__name__}: {exc}"[:300]}
        queues = {"status": "down", "worker_count": 0, "worker_names": [], "queues": {}}

    tasks = _task_journal_health()
    overall = _worst(
        database.get("status", "down"),
        redis_health.get("status", "down"),
        queues.get("status", "down"),
        tasks.get("status", "down"),
        config.get("status", "degraded"),
    )

    return {
        "ok": overall != "down",
        "ready": overall == "ok",
        "status": overall,
        "checked_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "database": database,
        "redis": redis_health,
        "rq": queues,
        "tasks": tasks,
        "configuration": config,
    }
