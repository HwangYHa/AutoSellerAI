from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from app.sqlite_runtime import is_sqlite_contention_error


def test_sqlite_connections_enable_busy_timeout_wal_and_foreign_keys(tmp_path):
    db_path = tmp_path / "runtime.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        busy_timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
        journal_mode = str(conn.exec_driver_sql("PRAGMA journal_mode").scalar_one()).lower()
        foreign_keys = conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        synchronous = conn.exec_driver_sql("PRAGMA synchronous").scalar_one()

    assert busy_timeout == 30_000
    assert journal_mode == "wal"
    assert foreign_keys == 1
    # SQLite: NORMAL == 1
    assert synchronous == 1


def test_only_transient_sqlite_contention_is_classified_for_retry():
    locked = OperationalError("INSERT", {}, Exception("database is locked"))
    already_exists = OperationalError("CREATE", {}, Exception("table threads_posts already exists"))
    unrelated = OperationalError("SELECT", {}, Exception("no such table: missing"))

    assert is_sqlite_contention_error(locked)
    assert is_sqlite_contention_error(already_exists)
    assert not is_sqlite_contention_error(unrelated)
