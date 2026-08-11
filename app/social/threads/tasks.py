from __future__ import annotations

import os
from typing import Any

from redis import Redis
from rq import Queue

from app.social.threads.service import process_event


def redis_connection() -> Redis:
    return Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))


def enqueue_webhook_event(event: dict[str, Any], auto_reply: bool = True) -> str:
    queue = Queue("threads", connection=redis_connection(), default_timeout=120)
    job = queue.enqueue(
        "app.social.threads.tasks.process_threads_webhook_event",
        event,
        auto_reply=auto_reply,
        job_timeout=120,
        result_ttl=3600,
        failure_ttl=86400,
    )
    return str(job.id)


def process_threads_webhook_event(event: dict[str, Any], auto_reply: bool = True) -> dict[str, Any]:
    return process_event(event, auto_reply=auto_reply)
