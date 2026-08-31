from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from redis import Redis
from rq import Queue, Worker
from rq.job import Job
from sqlalchemy import desc, select

from app.db import get_db
from app.image_studio.models import AIImageGeneration, ensure_image_studio_schema
from app.image_studio.prompt_builder import build_prompt
from app.image_studio.schemas import HumanImageRequest
from app.image_studio.sd_webui_client import StableDiffusionWebUIClient
from app.sqlite_runtime import retry_sqlite_write


def _redis() -> Redis:
    return Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _loads(value: str, fallback):
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def get_image_queue_status() -> dict[str, Any]:
    """Return a small, failure-safe runtime snapshot for GUI/API clients."""
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

    try:
        retry_sqlite_write(set_job_id, attempts=6)
    except Exception:
        # The RQ job is already authoritative; do not invalidate it because the
        # non-critical journal write briefly lost a SQLite lock race.
        pass

    with get_db() as db:
        return db.get(AIImageGeneration, row_id)


def get_generation(row_id: int) -> AIImageGeneration | None:
    ensure_image_studio_schema()
    with get_db() as db:
        return db.get(AIImageGeneration, int(row_id))


def list_generations(limit: int = 50, status: str = "") -> list[AIImageGeneration]:
    ensure_image_studio_schema()
    safe_limit = max(1, min(int(limit), 300))
    clean_status = str(status or "").strip().lower()
    with get_db() as db:
        stmt = select(AIImageGeneration)
        if clean_status:
            stmt = stmt.where(AIImageGeneration.status == clean_status)
        rows = db.scalars(stmt.order_by(desc(AIImageGeneration.created_at)).limit(safe_limit)).all()
        return list(rows)


def generation_to_dict(row: AIImageGeneration) -> dict[str, Any]:
    return {
        "id": row.id,
        "rq_job_id": row.rq_job_id,
        "status": row.status,
        "provider": row.provider,
        "preset": row.preset,
        "subject_summary": row.subject_summary,
        "request": _loads(row.request_json, {}),
        "prompt": row.prompt,
        "negative_prompt": row.negative_prompt,
        "payload": _loads(row.payload_json, {}),
        "response_info": _loads(row.response_info_json, {}),
        "image_paths": _loads(row.image_paths_json, []),
        "warnings": _loads(row.warnings_json, []),
        "error": row.error,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
    }


def _actual_seed(row: AIImageGeneration) -> int | None:
    info = _loads(row.response_info_json, {})
    if isinstance(info, dict):
        all_seeds = info.get("all_seeds")
        if isinstance(all_seeds, list) and all_seeds:
            try:
                return int(all_seeds[0])
            except (TypeError, ValueError):
                pass
        try:
            if info.get("seed") is not None:
                return int(info["seed"])
        except (TypeError, ValueError):
            pass
    return None


def retry_generation(row_id: int, *, same_seed: bool = False) -> AIImageGeneration:
    """Create a fresh queued generation from a prior immutable request snapshot."""
    source = get_generation(row_id)
    if not source:
        raise LookupError(f"AI image generation #{row_id} not found")
    request_data = _loads(source.request_json, {})
    if not isinstance(request_data, dict):
        raise ValueError("저장된 생성 요청을 복원할 수 없습니다.")
    if same_seed:
        seed = _actual_seed(source)
        if seed is not None:
            request_data["seed"] = seed
    else:
        request_data["seed"] = -1
    return create_generation(HumanImageRequest.model_validate(request_data))


def _set_status(row_id: int, status: str, *, error: str = "") -> None:
    def update() -> None:
        with get_db() as db:
            row = db.get(AIImageGeneration, int(row_id))
            if row:
                row.status = status
                if error:
                    row.error = error[:4000]
                db.commit()

    retry_sqlite_write(update, attempts=6)


def cancel_generation(row_id: int) -> dict[str, Any]:
    """Cancel a queued request or interrupt the single active WebUI generation.

    The image queue is intentionally serialized to one GPU-facing worker.  For a
    running request, AUTOMATIC1111's interrupt endpoint is therefore safe to use
    as the cancellation primitive for the current image job.
    """
    row = get_generation(row_id)
    if not row:
        raise LookupError(f"AI image generation #{row_id} not found")
    current = str(row.status or "").lower()
    if current in {"completed", "failed", "cancelled"}:
        return {"ok": True, "generation_id": row_id, "status": current, "changed": False}

    connection = _redis()
    if current == "queued" and row.rq_job_id:
        try:
            job = Job.fetch(row.rq_job_id, connection=connection)
            state = job.get_status(refresh=True)
            state_value = str(getattr(state, "value", state)).lower()
            if state_value in {"queued", "deferred", "scheduled"}:
                job.cancel()
                _set_status(row_id, "cancelled")
                return {"ok": True, "generation_id": row_id, "status": "cancelled", "changed": True}
        except Exception:
            # The worker may have picked the job between the DB read and RQ read;
            # fall through to WebUI interrupt handling.
            pass

    _set_status(row_id, "cancel_requested")
    try:
        StableDiffusionWebUIClient().interrupt()
    except Exception as exc:
        _set_status(row_id, "cancel_requested", error=f"WebUI interrupt 요청 실패: {exc}")
        return {
            "ok": False,
            "generation_id": row_id,
            "status": "cancel_requested",
            "changed": True,
            "error": str(exc),
        }
    return {"ok": True, "generation_id": row_id, "status": "cancel_requested", "changed": True}


def resolve_generation_image(row_id: int, image_index: int) -> Path:
    """Resolve one persisted image while preventing arbitrary filesystem reads."""
    row = get_generation(row_id)
    if not row:
        raise LookupError(f"AI image generation #{row_id} not found")
    paths = _loads(row.image_paths_json, [])
    if not isinstance(paths, list) or image_index < 0 or image_index >= len(paths):
        raise IndexError("image index out of range")

    root = Path(os.getenv("SD_IMAGE_OUTPUT_DIR", "data/generated/stable_diffusion")).expanduser().resolve()
    target = Path(str(paths[image_index])).expanduser().resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PermissionError("stored image path is outside the configured image root") from exc
    if not target.is_file():
        raise FileNotFoundError(str(target))
    return target


__all__ = [
    "create_generation",
    "get_generation",
    "list_generations",
    "generation_to_dict",
    "get_image_queue_status",
    "retry_generation",
    "cancel_generation",
    "resolve_generation_image",
]
