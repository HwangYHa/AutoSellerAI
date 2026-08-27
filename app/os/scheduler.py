"""Seller OS recurring scheduler with GUI-configurable database rules.

Rules support both interval scheduling and explicit clock slots such as
09:00, 13:00, 18:00. Schedule metadata is stored inside payload_json under
`_schedule` so existing databases require no destructive migration.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from redis import Redis

from app.config import get_settings
from app.db import get_db
from app.os.commerce_automation_models import OSSchedulerRule
from app.os.schema import ensure_os_schema
from app.os.task_recovery import recover_stale_safe_tasks
from app.os.tasks import enqueue_task

logger = logging.getLogger(__name__)
MAINTENANCE_RESET_KEY = "seller-os:maintenance:reset"
SCHEDULE_META_KEY = "_schedule"

DEFAULT_JOBS = {
    "order_sync": {"default_minutes": 1, "payload": {"hours": 24}, "queue": "sync", "description": "쿠팡/스마트스토어 신규 주문 수집"},
    "claim_sync": {"default_minutes": 1, "payload": {"hours": 24}, "queue": "sync", "description": "취소·반품·교환 변경분 수집"},
    "payment_sync": {"default_minutes": 1, "payload": {"limit": 100}, "queue": "automation", "description": "카드앱/API 결제상태 확인"},
    "fulfillment_cycle": {"default_minutes": 1, "payload": {}, "queue": "automation", "description": "발주·송장 자동화 사이클"},
    "inquiry_sync": {"default_minutes": 5, "payload": {}, "queue": "sync", "description": "상품/구매자 문의 수집"},
    "inventory_automation": {"default_minutes": 5, "payload": {"confirmations": 2}, "queue": "automation", "description": "안전재고 품절·재입고 감시"},
    "settlement_sync": {"default_minutes": 60, "payload": {"days": 7}, "queue": "sync", "description": "판매채널 정산 내역 수집"},
    "catalog_sync": {"default_minutes": 60, "payload": {}, "queue": "sync", "description": "판매상품 동기화"},
    "data_reconcile": {"default_minutes": 30, "payload": {"remote": False}, "queue": "sync", "description": "데이터 관계 정합성 복구"},
}
SAFE_JOBS = DEFAULT_JOBS


def _enabled() -> bool:
    return str(os.getenv("SELLER_SCHEDULER_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on", "y"}


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=3, socket_timeout=5)


def _bucket(interval_minutes: int, now: float | None = None) -> int:
    return int((now or time.time()) // (max(1, interval_minutes) * 60))


def _normalize_clock(value: str) -> str:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(f"잘못된 실행시각: {text}")
    hour, minute = int(parts[0]), int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"잘못된 실행시각: {text}")
    return f"{hour:02d}:{minute:02d}"


def normalize_schedule_meta(value: object) -> dict:
    """Validate GUI schedule metadata and return a canonical shape."""
    if not isinstance(value, dict):
        return {"mode": "interval"}
    mode = str(value.get("mode") or "interval").strip().lower()
    if mode != "times":
        return {"mode": "interval"}
    timezone_name = str(value.get("timezone") or "Asia/Seoul").strip()
    try:
        ZoneInfo(timezone_name)
    except Exception as exc:
        raise ValueError(f"지원하지 않는 타임존: {timezone_name}") from exc
    raw_times = value.get("at") or []
    if isinstance(raw_times, str):
        raw_times = [x.strip() for x in raw_times.replace(";", ",").split(",") if x.strip()]
    times = sorted({_normalize_clock(str(x)) for x in raw_times})
    if not times:
        raise ValueError("시간지정 스케줄은 실행시각이 1개 이상 필요합니다.")
    weekdays_raw = value.get("weekdays")
    if weekdays_raw in (None, "", []):
        weekdays = list(range(7))
    else:
        weekdays = sorted({int(x) for x in weekdays_raw if 0 <= int(x) <= 6})
        if not weekdays:
            raise ValueError("weekdays는 0(월)~6(일) 중 1개 이상이어야 합니다.")
    return {"mode": "times", "timezone": timezone_name, "at": times, "weekdays": weekdays}


def ensure_default_scheduler_rules() -> None:
    ensure_os_schema()
    with get_db() as db:
        existing = {x.task_type for x in db.query(OSSchedulerRule).all()}
        changed = False
        for task_type, spec in DEFAULT_JOBS.items():
            if task_type in existing:
                continue
            db.add(OSSchedulerRule(
                task_type=task_type,
                enabled=True,
                interval_minutes=int(spec["default_minutes"]),
                queue_name=str(spec["queue"]),
                payload_json=json.dumps(spec["payload"], ensure_ascii=False),
                description=str(spec["description"]),
            ))
            changed = True
        if changed:
            db.commit()


def _job_rules() -> list[dict]:
    ensure_default_scheduler_rules()
    with get_db() as db:
        rows = db.query(OSSchedulerRule).order_by(OSSchedulerRule.task_type).all()
        result = []
        for row in rows:
            try:
                payload = json.loads(row.payload_json or "{}")
                if not isinstance(payload, dict):
                    payload = {}
            except Exception:
                payload = {}
            try:
                schedule = normalize_schedule_meta(payload.get(SCHEDULE_META_KEY))
            except ValueError as exc:
                logger.error("invalid scheduler rule task=%s: %s", row.task_type, exc)
                schedule = {"mode": "invalid", "error": str(exc)}
            result.append({
                "id": row.id,
                "task_type": row.task_type,
                "enabled": bool(row.enabled),
                "interval_minutes": max(1, int(row.interval_minutes or 1)),
                "queue": row.queue_name or "sync",
                "payload": payload,
                "schedule": schedule,
            })
        return result


def _due_slot(spec: dict, timestamp: float) -> str | None:
    schedule = spec.get("schedule") or {"mode": "interval"}
    if schedule.get("mode") == "invalid":
        return None
    if schedule.get("mode") != "times":
        return f"interval:{_bucket(int(spec['interval_minutes']), timestamp)}"

    tz = ZoneInfo(str(schedule.get("timezone") or "Asia/Seoul"))
    local = datetime.fromtimestamp(timestamp, tz)
    if local.weekday() not in set(schedule.get("weekdays") or range(7)):
        return None
    clock = local.strftime("%H:%M")
    if clock not in set(schedule.get("at") or []):
        return None
    return f"clock:{local.strftime('%Y%m%d')}:{clock}"


def _task_payload(payload: dict) -> dict:
    cleaned = dict(payload or {})
    cleaned.pop(SCHEDULE_META_KEY, None)
    return cleaned


def schedule_due_jobs(redis: Redis | None = None, *, now: float | None = None) -> list[dict]:
    if not _enabled():
        return []
    redis = redis or _redis()
    if redis.exists(MAINTENANCE_RESET_KEY):
        return []
    timestamp = now or time.time()
    results: list[dict] = []
    for spec in _job_rules():
        if not spec["enabled"]:
            continue
        slot = _due_slot(spec, timestamp)
        if not slot:
            continue
        task_type = spec["task_type"]
        marker = f"seller-os:schedule:{task_type}:{slot}"
        claimed = redis.set(marker, "1", nx=True, ex=172800)
        if not claimed:
            continue
        result = enqueue_task(
            task_type,
            _task_payload(dict(spec["payload"])),
            queue_name=str(spec["queue"]),
            # Keep one logical scheduler task of each type running at once. The slot
            # marker separately prevents duplicate enqueue within the same minute.
            dedupe_key=f"scheduled:{task_type}",
        )
        if result.get("ok"):
            with get_db() as db:
                row = db.query(OSSchedulerRule).filter_by(id=int(spec["id"])).first()
                if row:
                    row.last_enqueued_at = datetime.utcnow()
                    db.commit()
        results.append({"task_type": task_type, "slot": slot, **result})
    return results


def run_forever() -> None:
    logging.basicConfig(level=getattr(logging, str(get_settings().log_level).upper(), logging.INFO))
    logger.info("Seller OS scheduler started")
    next_recovery_at = 0.0
    while True:
        try:
            redis = _redis()
            if redis.exists(MAINTENANCE_RESET_KEY):
                logger.warning("Seller OS maintenance reset lock active; scheduling paused")
                time.sleep(30)
                continue
            now_mono = time.monotonic()
            if now_mono >= next_recovery_at:
                recovery = recover_stale_safe_tasks(redis)
                if recovery.get("reconciled"):
                    logger.info("reconciled completed RQ jobs count=%s ids=%s", recovery.get("reconciled"), recovery.get("reconciled_task_ids"))
                if recovery.get("orphaned"):
                    logger.warning("marked missing safe RQ jobs orphaned count=%s ids=%s", recovery.get("orphaned"), recovery.get("orphaned_task_ids"))
                if recovery.get("failed"):
                    logger.warning("reconciled failed RQ jobs count=%s ids=%s", recovery.get("failed"), recovery.get("failed_task_ids"))
                next_recovery_at = now_mono + 60.0
            for row in schedule_due_jobs(redis):
                logger.info("scheduled %s slot=%s task_id=%s ok=%s", row["task_type"], row.get("slot"), row.get("task_id"), row.get("ok"))
        except Exception:
            logger.exception("Seller OS scheduler iteration failed")
        time.sleep(30)


if __name__ == "__main__":
    run_forever()
