"""Database runtime bootstrap for Seller OS v3.

Local mode keeps the existing SQLite file for zero-friction migration. Production
may provide DATABASE_URL (normally PostgreSQL). Both legacy bridge code and v3 use
the same SQLAlchemy engine so there is one source of truth during migration.
"""
from __future__ import annotations

import time

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError

import app.db as legacy_db
from app.config import get_settings


_configured = False
_SQLITE_BUSY_TIMEOUT_MS = 30_000


def _is_locked(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message or "database schema is locked" in message


def _enable_sqlite_wal(engine) -> None:
    """Enable persistent WAL mode without making every DB connection change journals.

    journal_mode is a database-level setting and can itself require a lock. Do it
    once during bootstrap with a short bounded retry. Failure is non-fatal because
    busy_timeout still protects ordinary local writes and the next process start
    can retry WAL activation.
    """
    for attempt in range(5):
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
                conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            return
        except OperationalError as exc:
            if not _is_locked(exc) or attempt == 4:
                return
            time.sleep(0.10 * (2 ** attempt))


def configure_database() -> None:
    global _configured
    if _configured:
        return

    settings = get_settings()
    database_url = str(getattr(settings, "database_url", "") or "").strip()

    if database_url and legacy_db._engine is None:
        kwargs = {"pool_pre_ping": True, "future": True}
        if database_url.startswith("sqlite"):
            kwargs["connect_args"] = {
                "check_same_thread": False,
                "timeout": _SQLITE_BUSY_TIMEOUT_MS / 1000,
            }
        legacy_db._engine = create_engine(database_url, **kwargs)
        legacy_db._SessionLocal = None

    engine = legacy_db._get_engine()
    if engine.dialect.name == "sqlite":
        # Apply connection-local pragmas to every newly checked-out DBAPI handle.
        # WAL is deliberately NOT changed here: journal_mode is database-wide and
        # attempting to change it on each connection can create more contention.
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ARG001
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
            finally:
                cursor.close()

        # The legacy engine may have been created before Seller OS was imported.
        # Dispose idle pooled handles so subsequent connections consistently receive
        # the pragmas above. configure_database() runs before Seller OS sessions.
        engine.dispose()
        _enable_sqlite_wal(engine)

    _configured = True


def database_mode() -> str:
    configure_database()
    return legacy_db._get_engine().dialect.name
