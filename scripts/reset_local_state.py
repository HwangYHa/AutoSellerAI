"""Safely reset AutoSellerAI local SQLite/Redis state.

Run with Docker services stopped. The script always creates a SQLite backup first.

Examples:
  python scripts/reset_local_state.py --scope runtime --confirm RESET_RUNTIME
  python scripts/reset_local_state.py --scope all --confirm RESET_ALL_DATA

``runtime`` clears task/worker operational state and RQ scheduling keys while
preserving products, orders, Threads OAuth credentials and other business data.
``all`` removes the SQLite database and flushes the configured Redis DB. It is a
true destructive reset and therefore uses a different confirmation phrase.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from redis import Redis


RUNTIME_TABLES = (
    "os_background_tasks",
    "job_run_logs",
    "health_check_logs",
    "notification_logs",
)
RUNTIME_REDIS_PATTERNS = (
    "rq:*",
    "seller-os:schedule:*",
)


def _db_path() -> Path:
    return Path(os.getenv("DB_PATH", "data/autoseller.db")).resolve()


def _backup_database(db_path: Path) -> Path | None:
    if not db_path.exists():
        return None
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{db_path.stem}-{stamp}{db_path.suffix}.bak"
    shutil.copy2(db_path, target)
    return target


def _existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def _reset_runtime_sqlite(db_path: Path) -> list[str]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=OFF")
        existing = _existing_tables(conn)
        cleared: list[str] = []
        for table in RUNTIME_TABLES:
            if table not in existing:
                continue
            conn.execute(f'DELETE FROM "{table}"')
            cleared.append(table)
        conn.commit()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError:
            pass
        return cleared
    finally:
        conn.close()


def _redis() -> Redis:
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return Redis.from_url(url, socket_connect_timeout=3, socket_timeout=5)


def _delete_redis_patterns(redis: Redis, patterns: tuple[str, ...]) -> int:
    deleted = 0
    seen: set[bytes] = set()
    for pattern in patterns:
        for key in redis.scan_iter(match=pattern, count=500):
            if key in seen:
                continue
            seen.add(key)
            deleted += int(redis.delete(key) or 0)
    return deleted


def _remove_sqlite_files(db_path: Path) -> list[str]:
    removed: list[str] = []
    candidates = [
        db_path,
        Path(str(db_path) + "-wal"),
        Path(str(db_path) + "-shm"),
        Path(str(db_path) + ".write.lock"),
    ]
    for path in candidates:
        if path.exists():
            path.unlink()
            removed.append(str(path))
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset AutoSellerAI local state safely")
    parser.add_argument("--scope", choices=("runtime", "all"), required=True)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    expected = "RESET_RUNTIME" if args.scope == "runtime" else "RESET_ALL_DATA"
    if args.confirm != expected:
        parser.error(f"--scope {args.scope} requires --confirm {expected}")

    db_path = _db_path()
    backup = _backup_database(db_path)
    if backup:
        print(f"SQLite backup: {backup}")
    else:
        print(f"SQLite database does not exist yet: {db_path}")

    redis = _redis()
    redis.ping()

    if args.scope == "runtime":
        cleared = _reset_runtime_sqlite(db_path)
        redis_deleted = _delete_redis_patterns(redis, RUNTIME_REDIS_PATTERNS)
        print("Runtime reset complete")
        print(f"Cleared SQLite tables: {', '.join(cleared) if cleared else '(none)'}")
        print(f"Deleted Redis keys: {redis_deleted}")
        print("Preserved business/product/order data and Threads OAuth credentials.")
        return 0

    removed = _remove_sqlite_files(db_path)
    redis.flushdb()
    print("FULL local data reset complete")
    print(f"Removed SQLite files: {', '.join(removed) if removed else '(none)'}")
    print("Redis DB flushed.")
    print("Threads OAuth credentials and all local business data were removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
