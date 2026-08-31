from __future__ import annotations

import json
import os
from typing import Any

from redis import Redis
from rq import Queue, Worker
from sqlalchemy import desc, select

from app.db import get_db
from app.image_studio.models import AIImageGeneration, ensure_image_studio_schema
from app.image_studio.prompt_builder import build_prompt
from app.image_studio.schemas import HumanImageRequest
from app.sqlite_runtime import retry_sqlite_write


def _redis() -> Redis:
    return Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def get_image_queue_status() -> dict[str, Any]:
    """Return a small, failure-safe runtime snapshot for the Streamlit studio."""
    try:
        connection = _redis()
        connection.ping()
        queue = Queue("image", connection=connection)
        workers = Worker.all(queue=queue)
        worker_rows = []
        for worker in workers:
            state = getattr(worker, "state", "unknown")
            state_value = getattr(state, "value", state)
            worker_rows.append(
                {
                    "name": str(getattr(worker, "name", "") or ""),
                    "state": str(state_value or "unknown"),
                    "last_heartbeat": getattr(worker, "last_heartbeat", None),
                }
            )
        return {
            "ok": True,
            "queued": int(queue.count),
            "workers": len(worker_rows),
            "worker_rows": worker_rows,
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "queued": 0,
            "workers": 0,
            "worker_rows": [],
            "error": str(exc),
        }


def create_generation(request: HumanImageRequest) -> AIImageGeneration:
    """Persist a generation request and enqueue it on the dedicated image queue."""
    ensure_image_studio_schema()
    bundle = build_prompt(request)

    def insert() -> int:
        with get_db() as db:
            row = AIImageGeneration(
                status="queued",
                preset=request.preset,
                subject_summary=bundle.subject_summary,
                request_json=request.model_dump_json(),
                prompt=bundle.positive,
                negative_prompt=bundle.negative,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id

    row_id = retry_sqlite_write(insert, attempts=6)

    try:
        from app.image_studio.tasks import run_generation_job

        queue = Queue("image", connection=_redis(), default_timeout=int(os.getenv("SD_WEBUI_TIMEOUT_SECONDS", "900")))
        job = queue.enqueue(
            run_generation_job,
            row_id,
            job_timeout=int(os.getenv("SD_WEBUI_TIMEOUT_SECONDS", "900")),
            result_ttl=86400,
            failure_ttl=604800,
        )
    except Exception as exc:
        # Only a genuine Redis/RQ enqueue failure marks the request failed.  A
        # later SQLite journal update must not invalidate a job that is already
        # present in Redis and may already be running.
        def mark_failed() -> None:
            with get_db() as db:
                row = db.get(AIImageGeneration, row_id)
                if row:
                    row.status = "failed"
                    row.error = f"이미지 작업 큐 등록 실패: {exc}"[:4000]
                    db.commit()

        retry_sqlite_write(mark_failed, attempts=6)
        raise RuntimeError(f"이미지 작업을 큐에 등록하지 못했습니다: {exc}") from exc

    def set_job_id() -> None:
        with get_db() as db:
            row = db.get(AIImageGeneration, row_id)
            if row:
                row.rq_job_id = job.id
                db.commit()

    # If this bookkeeping write is temporarily busy, surface the issue without
    # changing status to failed: the queued worker job remains authoritative.
    try:
        retry_sqlite_write(set_job_id, attempts=6)
    except Exception:
        pass

    with get_db() as db:
        return db.get(AIImageGeneration, row_id)


def get_generation(row_id: int) -> AIImageGeneration | None:
    ensure_image_studio_schema()
    with get_db() as db:
        return db.get(AIImageGeneration, int(row_id))


def list_generations(limit: int = 50) -> list[AIImageGeneration]:
    ensure_image_studio_schema()
    safe_limit = max(1, min(int(limit), 300))
    with get_db() as db:
        rows = db.scalars(select(AIImageGeneration).order_by(desc(AIImageGeneration.created_at)).limit(safe_limit)).all()
        return list(rows)


def generation_to_dict(row: AIImageGeneration) -> dict[str, Any]:
    def loads(value: str, fallback):
        try:
            return json.loads(value or "")
        except Exception:
            return fallback

    return {
        "id": row.id,
        "rq_job_id": row.rq_job_id,
        "status": row.status,
        "provider": row.provider,
        "preset": row.preset,
        "subject_summary": row.subject_summary,
        "request": loads(row.request_json, {}),
        "prompt": row.prompt,
        "negative_prompt": row.negative_prompt,
        "payload": loads(row.payload_json, {}),
        "response_info": loads(row.response_info_json, {}),
        "image_paths": loads(row.image_paths_json, []),
        "warnings": loads(row.warnings_json, []),
        "error": row.error,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
    }


__all__ = [
    "create_generation",
    "get_generation",
    "list_generations",
    "generation_to_dict",
    "get_image_queue_status",
]
