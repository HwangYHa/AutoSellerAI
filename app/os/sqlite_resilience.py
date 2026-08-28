"""Small SQLite contention helpers used by Seller OS write paths.

SQLite is intentionally supported for local/single-PC operation.  It has a single
writer, so short overlapping writes from Streamlit, API and background workers may
raise ``database is locked`` even though the database is healthy.  Only that
specific transient condition is retried; unrelated database errors are surfaced.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

from sqlalchemy.exc import OperationalError


T = TypeVar("T")

_LOCK_MARKERS = (
    "database is locked",
    "database table is locked",
    "database schema is locked",
)


def is_sqlite_lock_error(exc: BaseException) -> bool:
    """Return True only for SQLite lock/busy OperationalError variants."""
    if not isinstance(exc, OperationalError):
        return False
    message = str(exc).lower()
    return any(marker in message for marker in _LOCK_MARKERS)


def run_with_sqlite_lock_retry(
    operation: Callable[[], T],
    *,
    attempts: int = 6,
    initial_delay_seconds: float = 0.10,
    max_delay_seconds: float = 1.50,
) -> T:
    """Retry one complete, transaction-safe operation on transient SQLite locks.

    The callable must create/close its own transaction per attempt so a failed
    attempt is rolled back before the next try.
    """
    total_attempts = max(1, int(attempts))
    delay = max(0.0, float(initial_delay_seconds))

    for attempt in range(total_attempts):
        try:
            return operation()
        except OperationalError as exc:
            if not is_sqlite_lock_error(exc) or attempt >= total_attempts - 1:
                raise
            if delay:
                time.sleep(delay)
            delay = min(max_delay_seconds, max(delay * 2, 0.05))

    raise RuntimeError("unreachable")
