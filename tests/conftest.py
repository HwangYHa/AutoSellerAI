"""Global pytest safety guard.

All tests must run against an isolated disposable SQLite database. This file is
loaded by pytest before test modules are imported, so application settings and
SQLAlchemy engines cannot accidentally bind to the operator's real local DB.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


_TEST_DB_PATH = Path(
    os.environ.get("AUTOSELLER_PYTEST_DB_PATH")
    or (Path(tempfile.gettempdir()) / f"autoseller_pytest_{os.getpid()}.db")
).resolve()

# Force isolation even when the developer's .env points at data/autoseller.db.
# GitHub Actions may opt into a specific disposable path with
# AUTOSELLER_PYTEST_DB_PATH; tests never inherit DB_PATH/DATABASE_URL from .env.
os.environ["DB_PATH"] = str(_TEST_DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ.setdefault("CLAUDE_API_KEY", "")
os.environ.setdefault("THREADS_AUTO_REPLY", "false")
os.environ["AUTOSELLER_TESTING"] = "1"

# Remove stale files from an interrupted prior pytest process using the same
# explicit override path. The PID-based default normally makes this unnecessary.
for suffix in ("", "-wal", "-shm", ".write.lock"):
    path = Path(f"{_TEST_DB_PATH}{suffix}")
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Delete the disposable pytest database and its SQLite sidecar files."""
    try:
        import app.db as legacy_db

        if legacy_db._engine is not None:
            legacy_db._engine.dispose()
    except Exception:
        pass

    for suffix in ("", "-wal", "-shm", ".write.lock"):
        path = Path(f"{_TEST_DB_PATH}{suffix}")
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
