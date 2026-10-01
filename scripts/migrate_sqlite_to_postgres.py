"""One-time SQLite to PostgreSQL bootstrap for AutoSellerAI."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import MetaData, create_engine, inspect, select, text

TARGET_URL = os.environ["DATABASE_URL"]
SOURCE_CANDIDATES = (
    Path(os.getenv("SQLITE_VOLUME_DB", "/sqlite/autoseller.db")),
    Path(os.getenv("LEGACY_DB_PATH", "/legacy/autoseller.db")),
)
MARKER_TABLE = "autoseller_migration_meta"
MARKER_KEY = "sqlite_to_postgres_v1"


def _source_path() -> Path | None:
    for path in SOURCE_CANDIDATES:
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def _is_complete(engine) -> bool:
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS autoseller_migration_meta "
            "(key VARCHAR(100) PRIMARY KEY, value VARCHAR(500) NOT NULL)"
        ))
        value = conn.execute(
            text("SELECT value FROM autoseller_migration_meta WHERE key=:key"),
            {"key": MARKER_KEY},
        ).scalar_one_or_none()
        return value == "complete"


def _has_existing_rows(engine, table_names: list[str]) -> bool:
    with engine.connect() as conn:
        existing = set(inspect(conn).get_table_names())
        preparer = conn.dialect.identifier_preparer
        for name in table_names:
            if name not in existing:
                continue
            qname = preparer.quote(name)
            count = int(conn.execute(text(f"SELECT COUNT(*) FROM {qname}")).scalar_one() or 0)
            if count > 0:
                return True
    return False


def _repair_sequences(conn, tables) -> None:
    preparer = conn.dialect.identifier_preparer
    for table in tables:
        pk = list(table.primary_key.columns)
        if len(pk) != 1:
            continue
        column = pk[0]
        try:
            is_integer = column.type.python_type is int
        except NotImplementedError:
            is_integer = False
        if not is_integer:
            continue
        sequence = conn.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": table.name, "column_name": column.name},
        ).scalar_one_or_none()
        if not sequence:
            continue
        qtable = preparer.quote(table.name)
        qcolumn = preparer.quote(column.name)
        max_id = int(
            conn.execute(text(f"SELECT COALESCE(MAX({qcolumn}), 0) FROM {qtable}")).scalar_one() or 0
        )
        if max_id > 0:
            conn.execute(
                text("SELECT setval(CAST(:sequence AS regclass), :value, true)"),
                {"sequence": sequence, "value": max_id},
            )


def migrate() -> None:
    target = create_engine(TARGET_URL, pool_pre_ping=True, future=True)
    if _is_complete(target):
        print("[db-bootstrap] PostgreSQL migration already complete")
        return

    source_path = _source_path()
    if source_path is None:
        print("[db-bootstrap] no SQLite source found; PostgreSQL starts empty")
        with target.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO autoseller_migration_meta(key,value) VALUES(:key,'complete') "
                    "ON CONFLICT (key) DO UPDATE SET value='complete'"
                ),
                {"key": MARKER_KEY},
            )
        return

    source = create_engine(
        f"sqlite:///{source_path}",
        connect_args={"check_same_thread": False, "timeout": 60},
        future=True,
    )
    metadata = MetaData()
    metadata.reflect(bind=source)
    tables = [
        table for name, table in metadata.tables.items()
        if not name.startswith("sqlite_") and name != MARKER_TABLE
    ]

    if _has_existing_rows(target, [table.name for table in tables]):
        raise RuntimeError(
            "PostgreSQL has application rows but the SQLite migration is not marked complete."
        )

    metadata.create_all(target)
    print(f"[db-bootstrap] migrating {source_path} to PostgreSQL")

    with source.connect() as src, target.begin() as dst:
        for table in tables:
            rows = src.execute(select(table)).mappings().all()
            if not rows:
                continue
            for offset in range(0, len(rows), 500):
                dst.execute(table.insert(), [dict(row) for row in rows[offset:offset + 500]])
            print(f"[db-bootstrap] {table.name}: {len(rows)} rows")
        _repair_sequences(dst, tables)
        dst.execute(
            text(
                "INSERT INTO autoseller_migration_meta(key,value) VALUES(:key,'complete') "
                "ON CONFLICT (key) DO UPDATE SET value='complete'"
            ),
            {"key": MARKER_KEY},
        )

    print("[db-bootstrap] SQLite to PostgreSQL migration complete")


if __name__ == "__main__":
    migrate()
