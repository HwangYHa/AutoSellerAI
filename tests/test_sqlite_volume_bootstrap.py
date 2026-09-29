from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.bootstrap_sqlite_volume import bootstrap_sqlite_volume


def _create_db(path: Path, value: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample (value) VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


def test_bootstrap_sqlite_volume_copies_legacy_db_once(tmp_path):
    legacy = tmp_path / "legacy.db"
    target = tmp_path / "native" / "autoseller.db"
    _create_db(legacy, "legacy")

    assert bootstrap_sqlite_volume(legacy, target) is True
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone() == ("legacy",)
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    # Existing target is authoritative and must never be overwritten on restart.
    with sqlite3.connect(target) as conn:
        conn.execute("UPDATE sample SET value='native'")
        conn.commit()

    assert bootstrap_sqlite_volume(legacy, target) is False
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone() == ("native",)


def test_bootstrap_sqlite_volume_allows_fresh_install(tmp_path):
    legacy = tmp_path / "missing.db"
    target = tmp_path / "native" / "autoseller.db"

    assert bootstrap_sqlite_volume(legacy, target) is False
    assert not target.exists()
