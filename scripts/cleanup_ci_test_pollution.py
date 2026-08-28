"""Preview or remove historical pytest/CI pollution from the operator database.

The old profit-cycle test created a synthetic product named ``CI 차량용 청소기``
with SKU prefix ``CI-PROFIT-`` and order IDs prefixed ``NAVER-CI-``. When pytest
was run locally without a test DB override those committed rows could land in the
real SQLite database.

This tool is deliberately narrow:
- preview is the default;
- deletion requires --apply;
- only rows linked to CI-PROFIT product IDs or explicit CI marker prefixes are
  eligible.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

from sqlalchemy import MetaData, Table, and_, delete, inspect, or_, select

from app.db import _get_engine


CI_PRODUCT_NAME = "CI 차량용 청소기"
CI_SKU_PREFIX = "CI-PROFIT-"
CI_ORDER_PREFIX = "NAVER-CI-"
CI_CAMPAIGN_PREFIX = "ci-profit-"
CI_THREADS_PREFIX = "threads-ci-"
CI_CLICK_PREFIX = "click-"


def _candidate_condition(table: Table, product_ids: list[int]):
    conditions = []
    c = table.c

    if product_ids and "product_id" in c:
        conditions.append(c.product_id.in_(product_ids))
    if "sku" in c:
        conditions.append(c.sku.like(f"{CI_SKU_PREFIX}%"))
    if "name" in c:
        conditions.append(c.name == CI_PRODUCT_NAME)
    if "product_name" in c:
        conditions.append(c.product_name == CI_PRODUCT_NAME)
    if "platform_order_id" in c:
        conditions.append(c.platform_order_id.like(f"{CI_ORDER_PREFIX}%"))
    if "campaign_key" in c:
        conditions.append(c.campaign_key.like(f"{CI_CAMPAIGN_PREFIX}%"))
    if "threads_post_id" in c:
        conditions.append(c.threads_post_id.like(f"{CI_THREADS_PREFIX}%"))
    if "click_id" in c:
        # The historical test generated click-<timestamp>-<index>. Restrict this
        # marker to rows already linked to CI product IDs when product_id exists.
        click_condition = c.click_id.like(f"{CI_CLICK_PREFIX}%")
        if product_ids and "product_id" in c:
            click_condition = and_(c.product_id.in_(product_ids), click_condition)
        conditions.append(click_condition)

    return or_(*conditions) if conditions else None


def inspect_pollution() -> tuple[list[int], dict[str, int]]:
    engine = _get_engine()
    metadata = MetaData()
    metadata.reflect(bind=engine)

    product_ids: list[int] = []
    products = metadata.tables.get("products")
    if products is not None and "id" in products.c:
        product_condition = or_(
            products.c.sku.like(f"{CI_SKU_PREFIX}%") if "sku" in products.c else False,
            products.c.name == CI_PRODUCT_NAME if "name" in products.c else False,
        )
        with engine.connect() as conn:
            product_ids = [int(x) for x in conn.execute(select(products.c.id).where(product_condition)).scalars().all()]

    counts: dict[str, int] = {}
    with engine.connect() as conn:
        for table in reversed(metadata.sorted_tables):
            condition = _candidate_condition(table, product_ids)
            if condition is None:
                continue
            count = len(conn.execute(select(table).where(condition)).fetchall())
            if count:
                counts[table.name] = count
    return product_ids, counts


def cleanup(*, apply: bool = False) -> dict[str, Any]:
    engine = _get_engine()
    metadata = MetaData()
    metadata.reflect(bind=engine)
    product_ids, preview = inspect_pollution()

    result: dict[str, Any] = {
        "apply": apply,
        "product_ids": product_ids,
        "matched": preview,
        "deleted": {},
    }
    if not apply or not preview:
        return result

    deleted = defaultdict(int)
    with engine.begin() as conn:
        # Delete children before parents according to reflected FK dependencies.
        for table in reversed(metadata.sorted_tables):
            condition = _candidate_condition(table, product_ids)
            if condition is None:
                continue
            response = conn.execute(delete(table).where(condition))
            if response.rowcount and response.rowcount > 0:
                deleted[table.name] += int(response.rowcount)

    result["deleted"] = dict(deleted)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove historical AutoSellerAI CI test rows safely")
    parser.add_argument("--apply", action="store_true", help="actually delete matched CI rows; default is preview only")
    args = parser.parse_args()

    result = cleanup(apply=args.apply)
    print("CI test pollution cleanup")
    print("mode:", "APPLY" if args.apply else "PREVIEW")
    print("product_ids:", result["product_ids"])
    print("matched:", result["matched"])
    if args.apply:
        print("deleted:", result["deleted"])
    elif result["matched"]:
        print("No rows were changed. Re-run with --apply after reviewing the preview.")
    else:
        print("No matching CI test rows found.")


if __name__ == "__main__":
    main()
