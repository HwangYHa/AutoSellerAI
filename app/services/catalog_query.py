"""Efficient catalog query path for Seller OS.

Unlike the legacy catalog query, this module does not load/normalize the entire
Product table on every Streamlit rerun. Counts are computed in SQL and only the
current page is converted to UI rows.
"""
from __future__ import annotations

from sqlalchemy import and_, func, or_

from app.db import Listing, Product, get_db
from app.services.product_catalog import SUPPLIER_SOURCES, _listing_map, _product_row

_EMPTY_IMAGES = (None, "", "[]", "null", "None")


def _needs_action_condition():
    failed_listing_exists = (
        get_db  # keep import grouping stable for static tooling
    )
    # SQLAlchemy exists() via relationship-free tables.
    from sqlalchemy import exists, select
    failed = exists(select(Listing.id).where(
        Listing.product_id == Product.id,
        Listing.status == "failed",
    ))
    missing_image = or_(Product.images.is_(None), Product.images.in_(["", "[]", "null", "None"]))
    bad_sell = Product.sell_price <= 0
    bad_supply = and_(Product.source.in_(list(SUPPLIER_SOURCES)), Product.supply_price <= 0)
    return or_(missing_image, bad_sell, bad_supply, failed)


def get_catalog_fast(
    *,
    search: str = "",
    status: str = "",
    source: str = "",
    channel: str = "",
    page: int = 1,
    page_size: int = 20,
    action_only: bool = False,
) -> dict:
    page = max(1, int(page))
    page_size = max(6, min(50, int(page_size)))

    with get_db() as db:
        q = db.query(Product)
        if search.strip():
            term = f"%{search.strip()}%"
            q = q.filter(or_(Product.name.ilike(term), Product.sku.ilike(term), Product.source_id.ilike(term)))
        if status:
            q = q.filter(Product.status == status)
        if source:
            q = q.filter(Product.source == source)
        if channel:
            q = q.filter(Product.id.in_(
                db.query(Listing.product_id).filter(
                    Listing.platform == channel,
                    Listing.status == "success",
                )
            ))
        if action_only:
            q = q.filter(_needs_action_condition())

        total = int(q.count())
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        rows = (
            q.order_by(Product.updated_at.desc(), Product.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        listing_map = _listing_map(db, [p.id for p in rows])
        items = [_product_row(p, listing_map.get(p.id, [])) for p in rows]

        total_products = int(db.query(func.count(Product.id)).scalar() or 0)
        listed = int(db.query(func.count(Product.id)).filter(Product.status == "listed").scalar() or 0)
        ready = int(db.query(func.count(Product.id)).filter(Product.status == "ready").scalar() or 0)
        no_image = int(db.query(func.count(Product.id)).filter(
            or_(Product.images.is_(None), Product.images.in_(["", "[]", "null", "None"]))
        ).scalar() or 0)
        needs_action = int(db.query(func.count(Product.id)).filter(_needs_action_condition()).scalar() or 0)

    return {
        "items": items,
        "total": total,
        "filtered_total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "metrics": {
            "total": total_products,
            "listed": listed,
            "ready": ready,
            "needs_action": needs_action,
            "no_image": no_image,
        },
    }
