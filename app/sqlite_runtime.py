"""Process-wide SQLite concurrency hardening.

AutoSellerAI runs several Docker processes against the same SQLite file
(Streamlit, APIs, workers and schedulers). SQLite permits many readers but only
one writer. WAL and busy_timeout reduce contention, but they cannot prevent two
independent SQLAlchemy sessions from trying to become the writer at the same
moment. This module therefore serializes ORM write transactions with a small
cross-process file mutex while leaving read-only sessions concurrent.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql.schema import MetaData

try:  # Linux/Docker/CI: real cross-process locking.
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows host fallback.
    fcntl = None  # type: ignore

T = TypeVar("T")

_BUSY_TIMEOUT_MS = 30_000
_SCHEMA_RETRY_DELAYS = (0.05, 0.10, 0.20, 0.40, 0.80, 1.60)
_WRITE_RETRY_DELAYS = (0.05, 0.10, 0.20, 0.40, 0.80)
_SESSION_LOCK_KEY = "_autoseller_sqlite_writer_lock"
_installed = False
_original_create_all = MetaData.create_all

# File locks coordinate Docker processes. This RLock additionally prevents
# concurrent writer sessions inside one Python process and is re-entrant for
# nested flushes on the same thread.
_process_writer_lock = threading.RLock()


def is_sqlite_contention_error(exc: BaseException) -> bool:
    """Return True only for transient SQLite concurrency/schema races."""
    text = str(exc).lower()
    return (
        "database is locked" in text
        or "database table is locked" in text
        or "database schema is locked" in text
        or "database is busy" in text
        or ("table " in text and " already exists" in text)
        or ("index " in text and " already exists" in text)
    )


def retry_sqlite_write(operation: Callable[[], T], *, attempts: int = 5) -> T:
    """Retry a small idempotent SQLite operation on transient lock errors.

    Callers must pass an operation that is safe to execute again. Arbitrary
    Session.commit() is intentionally not replayed because a failed flush makes
    the current SQLAlchemy transaction unusable until rollback.
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
        cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except Exception:
            # Another process can be switching the same DB to WAL during
            # startup. The next connection will observe/establish WAL mode.
            pass
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _sqlite_database_path(session: Session) -> Path | None:
    try:
        bind = session.get_bind()
        if getattr(bind.dialect, "name", "") != "sqlite":
            return None
        database = getattr(bind.url, "database", None)
        if not database or database == ":memory:":
            return None
        return Path(str(database)).expanduser().resolve()
    except Exception:
        return None


def _acquire_writer_lock(session: Session, _flush_context: Any, _instances: Any) -> None:
    """Take a DB-file writer mutex before the first ORM flush in a transaction."""
    if session.info.get(_SESSION_LOCK_KEY) is not None:
        return
    if not (session.new or session.dirty or session.deleted):
        return

    database_path = _sqlite_database_path(session)
    if database_path is None:
        return

    _process_writer_lock.acquire()
    lock_fd: int | None = None
    try:
        lock_path = Path(f"{database_path}.write.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        if fcntl is not None:
            # Blocking flock has no arbitrary 30-second failure window: a
            # short writer waits until the previous writer really commits.
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        session.info[_SESSION_LOCK_KEY] = lock_fd
    except Exception:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        _process_writer_lock.release()
        raise


def _release_writer_lock(session: Session, *_args: Any) -> None:
    lock_fd = session.info.pop(_SESSION_LOCK_KEY, None)
    if lock_fd is None:
        return
    try:
        if fcntl is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            os.close(lock_fd)
        except OSError:
            pass
    finally:
        _process_writer_lock.release()


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
    """Install SQLite safeguards once per Python process."""
    global _installed
    if _installed:
        return

    event.listen(Engine, "connect", _configure_sqlite_connection)
    MetaData.create_all = _create_all_with_retry  # type: ignore[method-assign]

    # ORM writes are serialized across all containers that share the DB file.
    # Commit/rollback releases the mutex. after_soft_rollback covers failed
    # flushes that transition the Session into a rollback-required state.
    event.listen(Session, "before_flush", _acquire_writer_lock)
    event.listen(Session, "after_commit", _release_writer_lock)
    event.listen(Session, "after_rollback", _release_writer_lock)
    event.listen(Session, "after_soft_rollback", _release_writer_lock)

    _installed = True


__all__ = [
    "install_sqlite_runtime",
    "is_sqlite_contention_error",
    "retry_sqlite_write",
]
