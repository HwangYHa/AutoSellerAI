"""Background-safe Seller OS maintenance task entrypoints."""
from __future__ import annotations

from typing import Any


def repair_all_product_images_task(include_marketplaces: bool = True) -> dict[str, Any]:
    from app.services.product_catalog import repair_all_product_images
    return repair_all_product_images(include_marketplaces=include_marketplaces)


def reconcile_data_graph_task(fetch_remote_identities: bool = True) -> dict[str, Any]:
    from app.services.data_graph import reconcile_data_graph
    return reconcile_data_graph(fetch_remote_identities=fetch_remote_identities)


def bulk_upload_products_task(product_ids: list[int], platforms: list[str]) -> dict[str, Any]:
    from app.pipeline import upload_product

    successes = 0
    failures: list[dict[str, Any]] = []
    for product_id in [int(x) for x in product_ids]:
        results = upload_product(product_id, list(platforms))
        if results and all(x.get("status") == "success" for x in results):
            successes += 1
        else:
            failures.append({"product_id": product_id, "results": results})
    return {
        "requested": len(product_ids),
        "successes": successes,
        "failures": failures[:30],
    }
