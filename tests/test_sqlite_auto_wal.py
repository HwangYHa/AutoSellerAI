from __future__ import annotations

import sqlite3

from sqlalchemy import create_engine


def test_file_backed_engine_auto_enables_wal_without_explicit_bootstrap(tmp_path):
    """Legacy app.db-style engines must get WAL without Seller OS configure_database()."""
    db_path = tmp_path / "legacy-direct.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    # No explicit ensure_sqlite_wal(engine) call here. The process-wide runtime
    # hook installed by importing the app package must bootstrap WAL itself.
    with engine.connect() as conn:
        journal_mode = str(conn.exec_driver_sql("PRAGMA journal_mode").scalar_one()).lower()
        busy_timeout = int(conn.exec_driver_sql("PRAGMA busy_timeout").scalar_one())

    assert journal_mode == "wal"
    assert busy_timeout == 30_000
    engine.dispose()


def test_wal_keeps_long_reader_from_blocking_product_style_update(tmp_path):
    """Regression: a UI/API reader must not make an UPDATE fail with database locked."""
    db_path = tmp_path / "reader-writer.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, detail_html TEXT)"
        )
        conn.exec_driver_sql(
            "INSERT INTO products (id, name, detail_html) VALUES (3140, 'before', '<p>before</p>')"
        )

    # Simulate another AutoSellerAI component holding a read transaction while it
    # performs non-DB work. In rollback-journal mode this reader blocks a writer;
    # in WAL mode the UPDATE is allowed to commit concurrently.
    reader = sqlite3.connect(str(db_path), timeout=0.2)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT name FROM products WHERE id = 3140").fetchone() == ("before",)

        with engine.begin() as writer:
            writer.exec_driver_sql(
                "UPDATE products SET name = ?, detail_html = ? WHERE id = ?",
                ("after", "<p>after</p>", 3140),
            )

        # The existing reader keeps its original snapshot until its transaction
        # ends, while a fresh connection sees the committed update.
        assert reader.execute("SELECT name FROM products WHERE id = 3140").fetchone() == ("before",)
        with engine.connect() as fresh:
            assert fresh.exec_driver_sql(
                "SELECT name, detail_html FROM products WHERE id = 3140"
            ).one() == ("after", "<p>after</p>")
    finally:
        reader.rollback()
        reader.close()
        engine.dispose()
