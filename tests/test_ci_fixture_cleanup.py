from __future__ import annotations

import sqlite3

from scripts.cleanup_ci_test_fixtures import _build_plan, _delete_ids


def test_ci_cleanup_targets_only_known_synthetic_markers(tmp_path):
    db_path = tmp_path / "cleanup.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT,
                name TEXT
            );
            CREATE TABLE platform_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                platform_order_id TEXT
            );
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                platform_order_id TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO products (sku, name) VALUES (?, ?)",
            ("CI-PROFIT-20260828", "CI 차량용 청소기"),
        )
        ci_product_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO products (sku, name) VALUES (?, ?)",
            ("REAL-001", "실제 판매 상품"),
        )
        real_product_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        conn.execute(
            "INSERT INTO platform_orders (product_id, platform_order_id) VALUES (?, ?)",
            (ci_product_id, "NAVER-CI-20260828-0"),
        )
        conn.execute(
            "INSERT INTO platform_orders (product_id, platform_order_id) VALUES (?, ?)",
            (real_product_id, "REAL-ORDER-001"),
        )
        conn.execute(
            "INSERT INTO orders (product_id, platform_order_id) VALUES (?, ?)",
            (ci_product_id, "NAVER-CI-20260828-0"),
        )
        conn.execute(
            "INSERT INTO orders (product_id, platform_order_id) VALUES (?, ?)",
            (real_product_id, "REAL-ORDER-001"),
        )
        conn.commit()

        plan = _build_plan(conn)
        assert plan["products"] == [ci_product_id]
        assert len(plan["platform_orders"]) == 1
        assert len(plan["orders"]) == 1

        for table, ids in plan.items():
            _delete_ids(conn, table, ids)
        conn.commit()

        products = conn.execute("SELECT sku, name FROM products ORDER BY id").fetchall()
        platform_orders = conn.execute("SELECT platform_order_id FROM platform_orders").fetchall()
        finance_orders = conn.execute("SELECT platform_order_id FROM orders").fetchall()

        assert products == [("REAL-001", "실제 판매 상품")]
        assert platform_orders == [("REAL-ORDER-001",)]
        assert finance_orders == [("REAL-ORDER-001",)]
    finally:
        conn.close()
