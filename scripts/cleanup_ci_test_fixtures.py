"""Find and remove leaked synthetic CI profit-cycle fixtures from a local SQLite DB.

The historical ``tests/test_threads_profit_cycle.py`` fixture used these unmistakable
identities and committed them:

- Product SKU: ``CI-PROFIT-*``
- Product name: ``CI 차량용 청소기``
- Marketplace order ID: ``NAVER-CI-*``
- Threads post/campaign IDs: ``threads-ci-*`` / ``ci-profit-*``

This tool deliberately targets only those markers. It is dry-run by default and
creates a SQLite-consistent backup before an actual delete.

Recommended usage (stop app/workers/schedulers first):

    python scripts/cleanup_ci_test_fixtures.py
    python scripts/cleanup_ci_test_fixtures.py --confirm DELETE_CI_TEST_DATA
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings


CONFIRMATION = "DELETE_CI_TEST_DATA"


def _database_path() -> Path:
    settings = get_settings()
    database_url = str(getattr(settings, "database_url", "") or "").strip()
    if database_url:
        url = make_url(database_url)
        if not url.drivername.startswith("sqlite"):
            raise RuntimeError(
                "이 정리 도구는 로컬 SQLite 전용입니다. "
                f"현재 DATABASE_URL 드라이버: {url.drivername}"
            )
        if not url.database or url.database == ":memory:":
            raise RuntimeError("파일 기반 SQLite DATABASE_URL이 아닙니다.")
        return Path(str(url.database)).expanduser().resolve()
    return Path(str(settings.db_path or "data/autoseller.db")).expanduser().resolve()


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _ids(conn: sqlite3.Connection, table: str, where: str, params: Iterable[Any] = ()) -> list[int]:
    if table not in _tables(conn) or "id" not in _columns(conn, table):
        return []
    rows = conn.execute(f'SELECT id FROM "{table}" WHERE {where}', tuple(params)).fetchall()
    return [int(row[0]) for row in rows]


def _where_in(column: str, values: list[int]) -> tuple[str, tuple[int, ...]] | None:
    if not values:
        return None
    return f'"{column}" IN ({",".join("?" for _ in values)})', tuple(values)


def _matching_ids(
    conn: sqlite3.Connection,
    table: str,
    *,
    id_filters: list[tuple[str, list[int]]] | None = None,
    text_filters: list[tuple[str, str]] | None = None,
) -> list[int]:
    if table not in _tables(conn):
        return []
    cols = _columns(conn, table)
    clauses: list[str] = []
    params: list[Any] = []
    for column, values in id_filters or []:
        if column not in cols or not values:
            continue
        where = _where_in(column, values)
        if where:
            clauses.append(where[0])
            params.extend(where[1])
    for column, pattern in text_filters or []:
        if column not in cols:
            continue
        clauses.append(f'"{column}" LIKE ?')
        params.append(pattern)
    if not clauses or "id" not in cols:
        return []
    rows = conn.execute(
        f'SELECT id FROM "{table}" WHERE ' + " OR ".join(f"({x})" for x in clauses),
        tuple(params),
    ).fetchall()
    return sorted({int(row[0]) for row in rows})


def _delete_ids(conn: sqlite3.Connection, table: str, ids: list[int]) -> int:
    if not ids or table not in _tables(conn):
        return 0
    total = 0
    for start in range(0, len(ids), 400):
        chunk = ids[start : start + 400]
        placeholders = ",".join("?" for _ in chunk)
        cur = conn.execute(f'DELETE FROM "{table}" WHERE id IN ({placeholders})', tuple(chunk))
        total += int(cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0)
    return total


def _build_plan(conn: sqlite3.Connection) -> dict[str, list[int]]:
    tables = _tables(conn)

    legacy_product_ids = _ids(
        conn,
        "products",
        'sku LIKE ? OR name = ?',
        ("CI-PROFIT-%", "CI 차량용 청소기"),
    )
    platform_order_ids = _matching_ids(
        conn,
        "platform_orders",
        id_filters=[("product_id", legacy_product_ids)],
        text_filters=[("platform_order_id", "NAVER-CI-%")],
    )
    finance_order_ids = _matching_ids(
        conn,
        "orders",
        id_filters=[("product_id", legacy_product_ids)],
        text_filters=[("platform_order_id", "NAVER-CI-%")],
    )

    thread_post_ids = _matching_ids(
        conn,
        "threads_posts",
        id_filters=[("product_id", legacy_product_ids)],
        text_filters=[("threads_post_id", "threads-ci-%"), ("campaign_key", "ci-profit-%")],
    )
    tracking_link_ids = _matching_ids(
        conn,
        "tracking_links",
        id_filters=[("product_id", legacy_product_ids), ("post_id", thread_post_ids)],
        text_filters=[("campaign_key", "ci-profit-%")],
    )
    social_draft_ids = _matching_ids(
        conn,
        "social_content_drafts",
        id_filters=[("product_id", legacy_product_ids), ("tracking_link_id", tracking_link_ids)],
    )
    scheduled_post_ids = _matching_ids(
        conn,
        "scheduled_social_posts",
        id_filters=[
            ("product_id", legacy_product_ids),
            ("draft_id", social_draft_ids),
            ("tracking_link_id", tracking_link_ids),
        ],
        text_filters=[("threads_post_id", "threads-ci-%"), ("campaign_key", "ci-profit-%")],
    )
    tracking_click_ids = _matching_ids(
        conn, "tracking_clicks", id_filters=[("tracking_link_id", tracking_link_ids)]
    )
    attribution_ids = _matching_ids(
        conn,
        "order_attributions",
        id_filters=[("product_id", legacy_product_ids), ("tracking_link_id", tracking_link_ids)],
        text_filters=[("platform_order_id", "NAVER-CI-%"), ("campaign_key", "ci-profit-%")],
    )
    profit_snapshot_ids = _matching_ids(
        conn,
        "content_profit_snapshots",
        id_filters=[("product_id", legacy_product_ids), ("post_id", thread_post_ids)],
        text_filters=[("threads_post_id", "threads-ci-%"), ("campaign_key", "ci-profit-%")],
    )
    strategy_profile_ids = _matching_ids(
        conn,
        "content_strategy_profiles",
        id_filters=[("product_id", legacy_product_ids)],
    )

    # The legacy -> Seller OS bridge copies the same synthetic product/orders into
    # the canonical os_* tables. Identify both by product marker and external order.
    os_product_ids = _ids(
        conn,
        "os_products",
        'sku LIKE ? OR name = ?',
        ("CI-PROFIT-%", "CI 차량용 청소기"),
    )
    os_order_ids = _matching_ids(
        conn,
        "os_sales_orders",
        text_filters=[("external_order_id", "NAVER-CI-%")],
    )
    os_order_item_ids = _matching_ids(
        conn,
        "os_sales_order_items",
        id_filters=[("order_id", os_order_ids), ("product_id", os_product_ids)],
        text_filters=[("product_name", "CI 차량용 청소기")],
    )
    os_fulfillment_ids = _matching_ids(
        conn, "os_fulfillments", id_filters=[("order_item_id", os_order_item_ids)]
    )
    os_listing_ids = _matching_ids(
        conn, "os_listings", id_filters=[("product_id", os_product_ids)]
    )
    os_variant_ids = _matching_ids(
        conn, "os_product_variants", id_filters=[("product_id", os_product_ids)]
    )
    os_offer_ids = _matching_ids(
        conn,
        "os_supplier_offers",
        id_filters=[("product_id", os_product_ids), ("variant_id", os_variant_ids)],
    )

    plan: dict[str, list[int]] = {
        # deepest social/analytics dependencies first
        "tracking_clicks": tracking_click_ids,
        "order_attributions": attribution_ids,
        "content_profit_snapshots": profit_snapshot_ids,
        "content_strategy_profiles": strategy_profile_ids,
        "scheduled_social_posts": scheduled_post_ids,
        "social_content_drafts": social_draft_ids,
        "tracking_links": tracking_link_ids,
        "threads_posts": thread_post_ids,
        # canonical order dependencies
        "os_payment_sessions": _matching_ids(
            conn, "os_payment_sessions", id_filters=[("fulfillment_id", os_fulfillment_ids)]
        ),
        "os_settlement_lines": _matching_ids(
            conn, "os_settlement_lines", id_filters=[("order_item_id", os_order_item_ids)]
        ),
        "os_order_ops_states": _matching_ids(
            conn, "os_order_ops_states", id_filters=[("order_item_id", os_order_item_ids)]
        ),
        "os_order_work_meta": _matching_ids(
            conn, "os_order_work_meta", id_filters=[("order_item_id", os_order_item_ids)]
        ),
        "os_fulfillments": os_fulfillment_ids,
        "os_sales_order_items": os_order_item_ids,
        "os_sales_orders": os_order_ids,
        # canonical product dependencies
        "os_listing_variants": _matching_ids(
            conn,
            "os_listing_variants",
            id_filters=[("listing_id", os_listing_ids), ("variant_id", os_variant_ids)],
        ),
        "os_product_match_rules": _matching_ids(
            conn,
            "os_product_match_rules",
            id_filters=[("product_id", os_product_ids), ("variant_id", os_variant_ids), ("supplier_offer_id", os_offer_ids)],
        ),
        "os_offer_verifications": _matching_ids(
            conn, "os_offer_verifications", id_filters=[("offer_id", os_offer_ids)]
        ),
        "os_inventory_policies": _matching_ids(
            conn, "os_inventory_policies", id_filters=[("product_id", os_product_ids)]
        ),
        "os_inventory_automation_states": _matching_ids(
            conn, "os_inventory_automation_states", id_filters=[("product_id", os_product_ids)]
        ),
        "os_marketplace_inquiries": _matching_ids(
            conn,
            "os_marketplace_inquiries",
            id_filters=[("product_id", os_product_ids)],
            text_filters=[("external_order_id", "NAVER-CI-%")],
        ),
        "os_channel_settlements": _matching_ids(
            conn, "os_channel_settlements", text_filters=[("external_order_id", "NAVER-CI-%")]
        ),
        "os_order_claims": _matching_ids(
            conn, "os_order_claims", text_filters=[("external_order_id", "NAVER-CI-%")]
        ),
        "os_listings": os_listing_ids,
        "os_supplier_offers": os_offer_ids,
        "os_product_variants": os_variant_ids,
        "os_products": os_product_ids,
        # legacy financial/order rows then source product
        "orders": finance_order_ids,
        "platform_orders": platform_order_ids,
        "products": legacy_product_ids,
    }

    # Keep only real tables with rows to make dry-run output concise.
    return {table: ids for table, ids in plan.items() if table in tables and ids}


def _backup(conn: sqlite3.Connection, db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}-before-ci-cleanup-{stamp}{db_path.suffix}.bak"
    with sqlite3.connect(str(backup_path)) as target:
        conn.backup(target)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove leaked CI fixture product/order rows")
    parser.add_argument("--confirm", default="", help=f"actual delete requires {CONFIRMATION}")
    args = parser.parse_args()

    db_path = _database_path()
    if not db_path.exists():
        print(f"SQLite DB가 없습니다: {db_path}")
        return 0

    apply = args.confirm == CONFIRMATION
    if args.confirm and not apply:
        parser.error(f"실제 삭제는 --confirm {CONFIRMATION} 이 필요합니다.")

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        plan = _build_plan(conn)
        total = sum(len(ids) for ids in plan.values())

        print(f"Database: {db_path}")
        print("Target markers: CI-PROFIT-* / CI 차량용 청소기 / NAVER-CI-* / threads-ci-* / ci-profit-*")
        print(f"Matched rows: {total}")
        for table, ids in plan.items():
            print(f"  {table}: {len(ids)}")

        if not plan:
            print("정리할 CI 테스트 데이터가 없습니다.")
            return 0
        if not apply:
            print("DRY RUN입니다. 실제 삭제하려면:")
            print(f"  python scripts/cleanup_ci_test_fixtures.py --confirm {CONFIRMATION}")
            return 0

        backup_path = _backup(conn, db_path)
        print(f"Backup: {backup_path}")

        # We explicitly delete every known dependency above. Turning FK checks off
        # during this one transaction prevents bridge-era SET NULL/CASCADE behavior
        # from obscuring what the cleanup actually removed.
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN IMMEDIATE")
        deleted: dict[str, int] = {}
        try:
            for table, ids in plan.items():
                deleted[table] = _delete_ids(conn, table, ids)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError:
            pass

        print("CI 테스트 데이터 정리 완료")
        for table, count in deleted.items():
            if count:
                print(f"  deleted {table}: {count}")
        print(f"Backup retained at: {backup_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
