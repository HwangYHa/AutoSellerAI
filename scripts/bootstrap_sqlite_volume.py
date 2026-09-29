"""Bootstrap AutoSellerAI SQLite into a Docker named volume.

The old default database lives under ./data, which is bind-mounted from the host.
On Docker Desktop that filesystem is not ideal for SQLite WAL/locking semantics.
This script performs a one-time SQLite online backup into a Linux-native named
volume before any application container starts.

It is intentionally idempotent:
- If the target database already exists and is non-empty, do nothing.
- If no legacy database exists, create the target directory and let the app
  initialize a fresh database normally.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


LEGACY_DB = Path(os.getenv("LEGACY_DB_PATH", "/legacy/autoseller.db"))
TARGET_DB = Path(os.getenv("TARGET_DB_PATH", "/app/sqlite/autoseller.db"))


def bootstrap_sqlite_volume(legacy_db: Path, target_db: Path) -> bool:
    """Copy a legacy SQLite database once. Return True only when a copy occurs."""
    target_db.parent.mkdir(parents=True, exist_ok=True)

    if target_db.exists() and target_db.stat().st_size > 0:
        print(f"[sqlite-bootstrap] target already exists: {target_db}")
        return False

    if not legacy_db.exists() or legacy_db.stat().st_size == 0:
        print(f"[sqlite-bootstrap] no legacy DB found at {legacy_db}; fresh DB will be initialized")
        return False

    tmp_target = target_db.with_suffix(target_db.suffix + ".tmp")
    if tmp_target.exists():
        tmp_target.unlink()

    print(f"[sqlite-bootstrap] backing up {legacy_db} -> {target_db}")
    source = sqlite3.connect(f"file:{legacy_db}?mode=ro", uri=True, timeout=60)
    target = sqlite3.connect(str(tmp_target), timeout=60)
    try:
        source.execute("PRAGMA busy_timeout=60000")
        target.execute("PRAGMA busy_timeout=60000")
        source.backup(target, pages=1000, sleep=0.05)
        # Keep the copied file self-contained. The application enables WAL after
        # the atomic rename; doing it on the temporary name could create sidecars
        # tied to the temporary pathname.
        target.execute("PRAGMA journal_mode=DELETE")
        integrity = target.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]).lower() != "ok":
            raise RuntimeError(f"SQLite backup integrity check failed: {integrity}")
        target.commit()
    finally:
        target.close()
        source.close()

    os.replace(tmp_target, target_db)
    print(f"[sqlite-bootstrap] migration complete: {target_db}")
    return True


def main() -> None:
    bootstrap_sqlite_volume(LEGACY_DB, TARGET_DB)


if __name__ == "__main__":
    main()
