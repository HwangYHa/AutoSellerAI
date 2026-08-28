from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from app.os.sqlite_resilience import is_sqlite_lock_error, run_with_sqlite_lock_retry


def _op_error(message: str) -> OperationalError:
    return OperationalError("INSERT INTO t VALUES (?)", (1,), Exception(message))


def test_sqlite_lock_retry_succeeds_after_transient_locks(monkeypatch):
    monkeypatch.setattr("app.os.sqlite_resilience.time.sleep", lambda _: None)
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        if calls["count"] < 3:
            raise _op_error("database is locked")
        return {"ok": True}

    assert run_with_sqlite_lock_retry(operation, attempts=4) == {"ok": True}
    assert calls["count"] == 3


def test_non_lock_operational_error_is_not_retried(monkeypatch):
    monkeypatch.setattr("app.os.sqlite_resilience.time.sleep", lambda _: None)
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise _op_error("no such table: broken")

    with pytest.raises(OperationalError):
        run_with_sqlite_lock_retry(operation, attempts=6)
    assert calls["count"] == 1


def test_lock_detection_covers_sqlite_lock_variants():
    assert is_sqlite_lock_error(_op_error("database is locked"))
    assert is_sqlite_lock_error(_op_error("database table is locked"))
    assert is_sqlite_lock_error(_op_error("database schema is locked"))
    assert not is_sqlite_lock_error(_op_error("disk I/O error"))
