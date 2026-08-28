"""Database runtime bootstrap for Seller OS v3.

Local mode keeps the existing SQLite file for zero-friction migration. Production
may provide DATABASE_URL (normally PostgreSQL). Both legacy bridge code and v3 use
the same SQLAlchemy engine so there is one source of truth during migration.
"""
from __future__ import annotations

from sqlalchemy import create_engine

import app.db as legacy_db
from app.config import get_settings
from app.sqlite_runtime import ensure_sqlite_wal


_configured = False
_SQLITE_BUSY_TIMEOUT_MS = 30_000


def configure_database() -> None:
    """Configure the shared engine without duplicating SQLite connection hooks.

    ``app.sqlite_runtime`` owns all connection-local pragmas globally. This module
    only selects/reuses the engine and performs the database-wide WAL activation
    once. Keeping those responsibilities separate avoids journal-mode lock races.
    """
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
        # Drop any idle handles created before OS bootstrap, then enable WAL under
        # the same cross-process writer mutex used by ORM transactions. The runtime
        # function remembers successful initialization per Engine, so repeated
        # configure calls do not execute PRAGMA journal_mode again.
        engine.dispose()
        ensure_sqlite_wal(engine)

    _configured = True


def database_mode() -> str:
    configure_database()
    return legacy_db._get_engine().dialect.name
