from pathlib import Path

from app.sqlite_runtime import is_sqlite_contention_error


def test_schema_changed_is_transient_contention():
    assert is_sqlite_contention_error(RuntimeError("database schema has changed"))


def test_pricing_schema_uses_metadata_create_all_not_table_create():
    source = Path("app/pricing/models.py").read_text(encoding="utf-8")
    assert "Base.metadata.create_all(" in source
    ensure_block = source.split("def ensure_pricing_schema()", 1)[1]
    assert ".__table__.create(" not in ensure_block
    assert "tables=PRICING_TABLES" in ensure_block
