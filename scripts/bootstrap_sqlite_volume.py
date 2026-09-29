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


def main() -> None:
    TARGET_DB.parent.mkdir(parents=True, exist_ok=True)

    if TARGET_DB.exists() and TARGET_DB.stat().st_size > 0:
        print(f"[sqlite-bootstrap] target already exists: {TARGET_DB}")
        return

    if not LEGACY_DB.exists() or LEGACY_DB.stat().st_size == 0:
        print(f"[sqlite-bootstrap] no legacy DB found at {LEGACY_DB}; fresh DB will be initialized")
        return

    tmp_target = TARGET_DB.with_suffix(TARGET_DB.suffix + ".tmp")
    if tmp_target.exists():
        tmp_target.unlink()

    print(f"[sqlite-bootstrap] backing up {LEGACY_DB} -> {TARGET_DB}")
    source = sqlite3.connect(f"file:{LEGACY_DB}?mode=ro", uri=True, timeout=60)
    target = sqlite3.connect(str(tmp_target), timeout=60)
    try:
        source.execute("PRAGMA busy_timeout=60000")
        target.execute("PRAGMA busy_timeout=60000")
        source.backup(target, pages=1000, sleep=0.05)
        target.execute("PRAGMA journal_mode=WAL")
        target.execute("PRAGMA synchronous=NORMAL")
        integrity = target.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]).lower() != "ok":
            raise RuntimeError(f"SQLite backup integrity check failed: {integrity}")
        target.commit()
    finally:
        target.close()
        source.close()

    os.replace(tmp_target, TARGET_DB)
    print(f"[sqlite-bootstrap] migration complete: {TARGET_DB}")


if __name__ == "__main__":
    main()
