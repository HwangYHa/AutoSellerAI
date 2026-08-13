"""Process-local background jobs for Streamlit maintenance work.

The goal is to keep long supplier/marketplace operations away from the Streamlit
request/WebSocket lifecycle. Jobs continue even if the browser disconnects.

This intentionally has no Streamlit dependency. It is suitable for the local
Seller OS process and can later be swapped for RQ without changing the UI API.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="autoseller-bg")
_LOCK = Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_MAX_JOBS = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim_jobs() -> None:
    if len(_JOBS) <= _MAX_JOBS:
        return
    completed = [
        (job_id, row.get("finished_at") or row.get("created_at") or "")
        for job_id, row in _JOBS.items()
        if row.get("status") in {"success", "failed"}
    ]
    for job_id, _ in sorted(completed, key=lambda x: x[1])[: max(0, len(_JOBS) - _MAX_JOBS)]:
        _JOBS.pop(job_id, None)


def submit_background_job(name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """Submit a callable and return a stable job id immediately."""
    job_id = uuid4().hex
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id,
            "name": str(name),
            "status": "queued",
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": "",
        }
        _trim_jobs()

    def runner() -> None:
        with _LOCK:
            row = _JOBS.get(job_id)
            if not row:
                return
            row["status"] = "running"
            row["started_at"] = _now()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # background boundary: persist error for UI
            with _LOCK:
                row = _JOBS.get(job_id)
                if row:
                    row["status"] = "failed"
                    row["error"] = f"{type(exc).__name__}: {exc}"
                    row["finished_at"] = _now()
            return
        with _LOCK:
            row = _JOBS.get(job_id)
            if row:
                row["status"] = "success"
                row["result"] = result
                row["finished_at"] = _now()

    _EXECUTOR.submit(runner)
    return job_id


def get_background_job(job_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    with _LOCK:
        row = _JOBS.get(str(job_id))
        return deepcopy(row) if row else None


def clear_background_job(job_id: str | None) -> None:
    if not job_id:
        return
    with _LOCK:
        _JOBS.pop(str(job_id), None)
