"""Process-wide SQLite concurrency hardening.

AutoSellerAI runs several Docker processes against the same SQLite file
(Streamlit, APIs, workers and schedulers). SQLite permits many readers but only
one writer. WAL and busy_timeout reduce contention, while a shared file mutex
serializes ORM writers across containers that mount the same data directory.

``PRAGMA journal_mode=WAL`` is database-wide, so it must not run on every pooled
DBAPI connection. The runtime lazily enables WAL once per SQLAlchemy Engine on
its first logical connection. This is important for legacy/Streamlit code paths
that use ``app.db`` directly and never call Seller OS ``configure_database()``.
"""
from __future__ import annotations

import os
import threading
import time
import weakref
from pathlib import Path
from typing import Any, Callable, TypeVar

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
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
_WAL_RETRY_DELAYS = (0.10, 0.20, 0.40, 0.80, 1.60)
_SESSION_LOCK_KEY = "_autoseller_sqlite_writer_lock"
_installed = False
_original_create_all = MetaData.create_all

# File locks coordinate Docker processes. This RLock additionally prevents
# concurrent writer sessions inside one Python process and is re-entrant for
# nested flushes on the same thread.
_process_writer_lock = threading.RLock()
_wal_file_lock = threading.RLock()
_wal_init_lock = threading.Lock()
_wal_initialized_engines: "weakref.WeakSet[Engine]" = weakref.WeakSet()


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

    Callers must pass an operation that creates/closes its own transaction for
    every attempt. Replaying an already-failed SQLAlchemy Session is unsafe because
    a failed flush requires rollback before that Session can be reused.
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
    """Apply connection-local SQLite pragmas.

    ``journal_mode=WAL`` is deliberately absent here because this event runs for
    every newly-created DBAPI connection. WAL bootstrap is handled once per
    SQLAlchemy Engine by ``_auto_enable_sqlite_wal`` instead.
    """
    module = getattr(dbapi_connection.__class__, "__module__", "")
    if not module.startswith("sqlite3"):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _engine_database_path(engine: Engine) -> Path | None:
    try:
        if getattr(engine.dialect, "name", "") != "sqlite":
            return None
        database = getattr(engine.url, "database", None)
        if not database or database == ":memory:":
            return None
        return Path(str(database)).expanduser().resolve()
    except Exception:
        return None


def _sqlite_database_path(session: Session) -> Path | None:
    try:
        bind = session.get_bind()
        return _engine_database_path(bind)
    except Exception:
        return None


def _acquire_database_file_lock(database_path: Path) -> int:
    """Acquire the shared writer mutex for one SQLite database file."""
    _process_writer_lock.acquire()
    lock_fd: int | None = None
    try:
        lock_path = Path(f"{database_path}.write.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        if fcntl is not None:
            # Blocking flock has no arbitrary timeout window. A short writer waits
            # until the previous writer actually commits/rolls back.
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        return lock_fd
    except Exception:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        _process_writer_lock.release()
        raise


def _release_database_file_lock(lock_fd: int) -> None:
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


def _acquire_wal_file_lock(database_path: Path) -> int:
    """Serialize WAL bootstrap across processes without reusing the writer lock.

    The first database connection can be opened while an ORM flush already owns
    ``.write.lock``. A distinct WAL lock avoids self-deadlock while still ensuring
    that Docker services do not all try to transition journal mode at once.
    """
    _wal_file_lock.acquire()
    lock_fd: int | None = None
    try:
        lock_path = Path(f"{database_path}.wal.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        if fcntl is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        return lock_fd
    except Exception:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        _wal_file_lock.release()
        raise


def _release_wal_file_lock(lock_fd: int) -> None:
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
        _wal_file_lock.release()


def _enable_wal_on_connection(connection: Connection) -> bool:
    """Attempt one WAL bootstrap using an already-open, transaction-free connection."""
    engine = connection.engine
    database_path = _engine_database_path(engine)
    if database_path is None:
        return True

    with _wal_init_lock:
        if engine in _wal_initialized_engines:
            return True

        lock_fd = _acquire_wal_file_lock(database_path)
        try:
            connection.exec_driver_sql(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
            mode = str(connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one()).lower()
            if mode == "wal":
                _wal_initialized_engines.add(engine)
                return True
            return False
        except OperationalError as exc:
            if not is_sqlite_contention_error(exc):
                raise
            # Do not make an otherwise healthy read connection fail because another
            # process happened to hold the DB during bootstrap. A later connection
            # (or explicit ensure_sqlite_wal call) retries the transition.
            return False
        finally:
            _release_wal_file_lock(lock_fd)


def _auto_enable_sqlite_wal(connection: Connection) -> None:
    """Enable WAL on the first logical connection of every file-backed SQLite Engine."""
    _enable_wal_on_connection(connection)


def ensure_sqlite_wal(engine: Engine) -> bool:
    """Ensure persistent WAL mode for a file-backed SQLite Engine.

    Most callers no longer need to invoke this explicitly because the global
    ``engine_connect`` hook performs the same bootstrap lazily. This function is
    retained for startup checks and tests and provides bounded retries when the
    first transition meets transient contention.
    """
    database_path = _engine_database_path(engine)
    if database_path is None:
        return True
    if engine in _wal_initialized_engines:
        return True

    for attempt, delay in enumerate(_WAL_RETRY_DELAYS):
        try:
            # Creating the logical SQLAlchemy Connection fires engine_connect,
            # which performs the one-per-Engine WAL transition without recursion.
            with engine.connect():
                pass
        except OperationalError as exc:
            if not is_sqlite_contention_error(exc):
                raise

        if engine in _wal_initialized_engines:
            return True
        if attempt < len(_WAL_RETRY_DELAYS) - 1:
            time.sleep(delay)

    return False


def _acquire_writer_lock(session: Session, _flush_context: Any, _instances: Any) -> None:
    """Take a DB-file writer mutex before the first ORM flush in a transaction."""
    if session.info.get(_SESSION_LOCK_KEY) is not None:
        return
    if not (session.new or session.dirty or session.deleted):
        return

    database_path = _sqlite_database_path(session)
    if database_path is None:
        return

    lock_fd = _acquire_database_file_lock(database_path)
    session.info[_SESSION_LOCK_KEY] = lock_fd


def _release_writer_lock(session: Session, *_args: Any) -> None:
    lock_fd = session.info.pop(_SESSION_LOCK_KEY, None)
    if lock_fd is None:
        return
    _release_database_file_lock(lock_fd)


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
    event.listen(Engine, "engine_connect", _auto_enable_sqlite_wal)
    MetaData.create_all = _create_all_with_retry  # type: ignore[method-assign]

    # ORM writes are serialized across all containers that share the DB directory.
    # Commit/rollback releases the mutex. after_soft_rollback covers failed flushes
    # that transition the Session into a rollback-required state.
    event.listen(Session, "before_flush", _acquire_writer_lock)
    event.listen(Session, "after_commit", _release_writer_lock)
    event.listen(Session, "after_rollback", _release_writer_lock)
    event.listen(Session, "after_soft_rollback", _release_writer_lock)

    _installed = True


__all__ = [
    "ensure_sqlite_wal",
    "install_sqlite_runtime",
    "is_sqlite_contention_error",
    "retry_sqlite_write",
]
