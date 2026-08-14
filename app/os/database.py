"""Database runtime bootstrap for Seller OS v3.

Local mode keeps the existing SQLite file for zero-friction migration.  Production
may provide DATABASE_URL (normally PostgreSQL).  Both legacy bridge code and v3 use
the same SQLAlchemy engine so there is one source of truth during migration.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event

import app.db as legacy_db
from app.config import get_settings


_configured = False


def configure_database() -> None:
    global _configured
    if _configured:
        return

    settings = get_settings()
    database_url = str(getattr(settings, "database_url", "") or "").strip()

    if database_url and legacy_db._engine is None:
        kwargs = {"pool_pre_ping": True, "future": True}
        if database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        legacy_db._engine = create_engine(database_url, **kwargs)
        legacy_db._SessionLocal = None

    engine = legacy_db._get_engine()
    if engine.dialect.name == "sqlite":
        # SQLite remains a supported local/single-PC runtime, not the scale-out DB.
        # WAL + busy_timeout materially reduce lock contention between UI/API/RQ.
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ARG001
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=30000")
            finally:
                cursor.close()

    _configured = True


def database_mode() -> str:
    configure_database()
    return legacy_db._get_engine().dialect.name
