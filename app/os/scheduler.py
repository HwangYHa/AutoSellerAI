"""Seller OS safe recurring scheduler.

The scheduler never performs business work and never queues dangerous mutations.
It only places deduplicated safe sync/reconcile tasks onto Redis/RQ. A short Redis
leader lease prevents duplicate schedules if multiple scheduler processes start.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from redis import Redis

from app.config import get_settings
from app.os.tasks import enqueue_task

logger = logging.getLogger(__name__)

SAFE_JOBS = {
    "order_sync": {
        "interval_env": "SELLER_ORDER_SYNC_MINUTES",
        "default_minutes": 5,
        "payload": {"hours": 24},
        "queue": "sync",
    },
    "catalog_sync": {
        "interval_env": "SELLER_CATALOG_SYNC_MINUTES",
        "default_minutes": 60,
        "payload": {},
        "queue": "sync",
    },
    "data_reconcile": {
        "interval_env": "SELLER_RECONCILE_MINUTES",
        "default_minutes": 30,
        "payload": {"remote": False},
        "queue": "sync",
    },
}


def _enabled() -> bool:
    value = str(os.getenv("SELLER_SCHEDULER_ENABLED", "true")).strip().lower()
    return value in {"1", "true", "yes", "on", "y"}


def _minutes(job: dict) -> int:
    raw = os.getenv(job["interval_env"], str(job["default_minutes"]))
    try:
        return max(1, int(raw))
    except Exception:
        return int(job["default_minutes"])


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=3, socket_timeout=5)


def _bucket(interval_minutes: int, now: float | None = None) -> int:
    return int((now or time.time()) // (max(1, interval_minutes) * 60))


def schedule_due_jobs(redis: Redis | None = None, *, now: float | None = None) -> list[dict]:
    """Enqueue each safe job at most once per interval bucket."""
    if not _enabled():
        return []
    redis = redis or _redis()
    timestamp = now or time.time()
    results: list[dict] = []
    for task_type, spec in SAFE_JOBS.items():
        interval = _minutes(spec)
        bucket = _bucket(interval, timestamp)
        marker = f"seller-os:schedule:{task_type}:{bucket}"
        # SET NX + expiration makes scheduling idempotent across multiple processes.
        claimed = redis.set(marker, "1", nx=True, ex=max(120, interval * 60 * 2))
        if not claimed:
            continue
        result = enqueue_task(
            task_type,
            dict(spec["payload"]),
            queue_name=str(spec["queue"]),
            dedupe_key=f"scheduled:{task_type}:{bucket}",
        )
        results.append({"task_type": task_type, "interval_minutes": interval, **result})
    return results


def run_forever() -> None:
    logging.basicConfig(level=getattr(logging, str(get_settings().log_level).upper(), logging.INFO))
    logger.info("Seller OS safe scheduler started")
    while True:
        try:
            results = schedule_due_jobs()
            for row in results:
                logger.info("scheduled %s task_id=%s ok=%s", row["task_type"], row.get("task_id"), row.get("ok"))
        except Exception:
            logger.exception("Seller OS scheduler iteration failed")
        time.sleep(30)


if __name__ == "__main__":
    run_forever()
