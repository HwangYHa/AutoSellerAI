"""Process-wide SQLite concurrency hardening.

The application runs several Docker processes against the same SQLite file
(Streamlit, APIs, workers and schedulers).  SQLite supports that topology for
light workloads, but writers must be configured to wait instead of failing
immediately and concurrent schema bootstrap needs a small retry window.
"""
from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.schema import MetaData

T = TypeVar("T")

_BUSY_TIMEOUT_MS = 30_000
_SCHEMA_RETRY_DELAYS = (0.05, 0.10, 0.20, 0.40, 0.80, 1.60)
_WRITE_RETRY_DELAYS = (0.05, 0.10, 0.20, 0.40, 0.80)
_installed = False
_original_create_all = MetaData.create_all


def is_sqlite_contention_error(exc: BaseException) -> bool:
    """Return True only for transient SQLite concurrency/schema races."""
    text = str(exc).lower()
    return (
        "database is locked" in text
        or "database table is locked" in text
        or "database schema is locked" in text
        or ("table " in text and " already exists" in text)
        or ("index " in text and " already exists" in text)
    )


def retry_sqlite_write(operation: Callable[[], T], *, attempts: int = 5) -> T:
    """Retry a small idempotent SQLite operation on transient lock errors.

    Callers must pass an operation that is safe to execute again.  The helper
    intentionally does not retry arbitrary SQLAlchemy Session.commit() calls,
    because a failed flush requires the caller to rebuild its transaction.
    """
    attempts = max(1, int(attempts))
    for attempt in range(attempts):
        try:
            return operation()
        except OperationalError as exc:
            if not is_sqlite_contention_error(exc) or attempt >= attempts - 1:
                raise
            delay = _WRITE_RETRY_DELAYS[min(attempt, len(_WRITE_RETRY_DELAYS) - 1)]
            time.sleep(delay)
    raise RuntimeError("unreachable")


def _configure_sqlite_connection(dbapi_connection: Any, _connection_record: Any) -> None:
    module = getattr(dbapi_connection.__class__, "__module__", "")
    if not module.startswith("sqlite3"):
        return

    cursor = dbapi_connection.cursor()
    try:
        # Set the wait window before WAL because switching journal mode can
        # itself briefly contend during multi-process startup.
        cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except Exception:
            # Another process may be switching the same DB to WAL right now.
            # busy_timeout still protects normal writes; the next connection
            # will observe/establish WAL mode.
            pass
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _create_all_with_retry(
    self: MetaData,
    bind: Any,
    tables: Any = None,
    checkfirst: bool = True,
) -> None:
    """Make SQLAlchemy's check-then-create bootstrap tolerant of process races."""
    for attempt, delay in enumerate(_SCHEMA_RETRY_DELAYS):
        try:
            return _original_create_all(self, bind, tables=tables, checkfirst=checkfirst)
        except OperationalError as exc:
            if not is_sqlite_contention_error(exc) or attempt >= len(_SCHEMA_RETRY_DELAYS) - 1:
                raise
            time.sleep(delay)
    return None


def install_sqlite_runtime() -> None:
    """Install process-wide SQLite safeguards once per Python process."""
    global _installed
    if _installed:
        return
    event.listen(Engine, "connect", _configure_sqlite_connection)
    MetaData.create_all = _create_all_with_retry  # type: ignore[method-assign]
    _installed = True


__all__ = [
    "install_sqlite_runtime",
    "is_sqlite_contention_error",
    "retry_sqlite_write",
]
