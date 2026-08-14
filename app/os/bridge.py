"""Idempotent legacy -> Seller OS v3 migration bridge.

The bridge is deliberately one-way.  Existing integrations can keep writing legacy
rows while migration is in progress; Seller OS then reconciles them into the
canonical relational spine.  New application services should write v3 directly.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.db import (
    Listing,
    Order,
    PlatformOrder,
    Product,
    SupplierRawProduct,
    get_db,
)
from app.os.models import (
    OSFulfillment,
    OSListing,
    OSListingVariant,
    OSProduct,
    OSProductVariant,
    OSSalesOrder,
    OSSalesOrderItem,
    OSSettlementLine,
    OSSupplier,
    OSSupplierOffer,
)
from app.os.schema import ensure_os_schema


def _loads(value: str, default: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else default
    except Exception:
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _supplier(db, code: str) -> OSSupplier:
    code = (code or "unknown").strip().lower()
    row = db.query(OSSupplier).filter_by(code=code).first()
    if row:
        return row
    names = {
        "ownerclan": "오너클랜",
        "domeggook": "도매꾹",
        "domemai": "도매매",
        "onchannel": "온채널",
        "coupang_import": "쿠팡 가져오기",
        "smartstore_import": "스마트스토어 가져오기",
    }
    row = OSSupplier(code=code, name=names.get(code, code), enabled=not code.endswith("_import"))
    db.add(row)
    db.flush()
    return row


def _upsert_product(db, legacy: Product) -> OSProduct:
    row = db.query(OSProduct).filter_by(sku=legacy.sku).first()
    content = {
        "images": _loads(legacy.images, []),
        "detail_images": _loads(legacy.detail_images, []),
        "detail_html": legacy.detail_html or "",
        "legacy_product_id": legacy.id,
        "legacy_source": legacy.source,
        "legacy_source_id": legacy.source_id,
        "legacy_sell_price": int(round(float(legacy.sell_price or 0))),
    }
    status_map = {"draft": "draft", "ready": "ready", "listed": "active"}
    if not row:
        row = OSProduct(
            sku=legacy.sku,
            name=legacy.name,
            brand=legacy.brand or "",
            category=legacy.category or "",
            origin=legacy.origin or "",
            material=legacy.material or "",
            status=status_map.get(legacy.status, "draft"),
            product_type="dropship",
            content_json=_dumps(content),
        )
        db.add(row)
        db.flush()
    else:
        row.name = legacy.name
        row.brand = legacy.brand or ""
        row.category = legacy.category or ""
        row.origin = legacy.origin or ""
        row.material = legacy.material or ""
        row.content_json = _dumps(content)

    # Keep one default variant when the legacy option model cannot be mapped safely.
    # Structured supplier variants can later replace this through direct v3 adapters.
    variant = db.query(OSProductVariant).filter_by(product_id=row.id, option_key="__default__").first()
    if not variant:
        variant = OSProductVariant(
            product_id=row.id,
            sku=f"{row.sku}-DEFAULT",
            option_key="__default__",
            option_json=_dumps({"legacy_options": _loads(legacy.options, [])}),
            status="active",
        )
        db.add(variant)
        db.flush()
    return row


def _product_maps(db) -> tuple[dict[int, OSProduct], dict[int, OSProductVariant]]:
    product_map: dict[int, OSProduct] = {}
    variant_map: dict[int, OSProductVariant] = {}
    for legacy in db.query(Product).all():
        p = _upsert_product(db, legacy)
        product_map[legacy.id] = p
        variant = db.query(OSProductVariant).filter_by(product_id=p.id, option_key="__default__").first()
        if variant:
            variant_map[legacy.id] = variant
    return product_map, variant_map


def _sync_offers(db, product_map: dict[int, OSProduct], variant_map: dict[int, OSProductVariant]) -> int:
    changed = 0
    raw_by_key = {
        (str(x.supplier_id or ""), str(x.raw_id or "")): x
        for x in db.query(SupplierRawProduct).all()
    }
    for legacy in db.query(Product).all():
        os_product = product_map[legacy.id]
        supplier = _supplier(db, legacy.source)
        variant = variant_map.get(legacy.id)
        raw = raw_by_key.get((str(legacy.source or ""), str(legacy.source_id or "")))
        offer = db.query(OSSupplierOffer).filter_by(
            supplier_id=supplier.id,
            supplier_product_id=str(legacy.source_id or ""),
            supplier_variant_id="",
        ).first()
        raw_json = raw.raw_json if raw else "{}"
        stock = raw.raw_stock if raw else None
        moq = max(1, int(raw.raw_moq_value or 1)) if raw else 1
        if not offer:
            offer = OSSupplierOffer(
                supplier_id=supplier.id,
                product_id=os_product.id,
                variant_id=variant.id if variant else None,
                supplier_product_id=str(legacy.source_id or ""),
                supplier_variant_id="",
                source_url=legacy.source_url or "",
                supply_price_krw=int(round(float(legacy.supply_price or 0))),
                shipping_fee_krw=0,
                stock_qty=stock,
                moq=moq,
                status="active",
                raw_json=raw_json,
                last_synced_at=raw.updated_at if raw else legacy.updated_at,
            )
            db.add(offer)
            changed += 1
        else:
            offer.product_id = os_product.id
            offer.variant_id = variant.id if variant else None
            offer.supply_price_krw = int(round(float(legacy.supply_price or 0)))
            offer.stock_qty = stock
            offer.moq = moq
            offer.raw_json = raw_json
    return changed


def _sync_listings(db, product_map: dict[int, OSProduct], variant_map: dict[int, OSProductVariant]) -> tuple[int, dict[int, OSListing]]:
    changed = 0
    listing_map: dict[int, OSListing] = {}
    for legacy in db.query(Listing).all():
        product = product_map.get(legacy.product_id)
        if not product:
            continue
        row = db.query(OSListing).filter_by(product_id=product.id, platform=legacy.platform, account_key="default").first()
        mapped_status = "active" if legacy.status == "success" else "failed" if legacy.status == "failed" else "draft"
        if not row:
            row = OSListing(
                product_id=product.id,
                platform=legacy.platform,
                account_key="default",
                external_product_id=str(legacy.platform_id or ""),
                status=mapped_status,
                sale_price_krw=int(_loads(product.content_json, {}).get("legacy_sell_price", 0) or 0),
                title=product.name,
                error=legacy.error or "",
                last_synced_at=legacy.created_at,
            )
            db.add(row)
            db.flush()
            changed += 1
        else:
            if legacy.platform_id:
                row.external_product_id = str(legacy.platform_id)
            row.status = mapped_status
            row.error = legacy.error or ""
        listing_map[legacy.id] = row

        # Seed a listing variant with the best external item identity available.
        variant = variant_map.get(legacy.product_id)
        external_item_id = ""
        try:
            from app.services.data_graph import MarketplaceIdentity
            identity_priority = ["vendor_item_id", "channel_product_no", "seller_product_item_id"]
            for identity_type in identity_priority:
                ident = db.query(MarketplaceIdentity).filter_by(
                    listing_id=legacy.id,
                    platform=legacy.platform,
                    identity_type=identity_type,
                ).first()
                if ident and ident.identity_value:
                    external_item_id = str(ident.identity_value)
                    break
        except Exception:
            pass
        if external_item_id:
            lv = db.query(OSListingVariant).filter_by(listing_id=row.id, external_item_id=external_item_id).first()
            if not lv:
                db.add(OSListingVariant(
                    listing_id=row.id,
                    variant_id=variant.id if variant else None,
                    external_item_id=external_item_id,
                    sale_price_krw=row.sale_price_krw,
                    status="active" if row.status == "active" else "paused",
                    last_synced_at=row.last_synced_at,
                ))
    return changed, listing_map


def _find_os_listing(db, platform: str, product_id: int | None) -> OSListing | None:
    if not product_id:
        return None
    return db.query(OSListing).filter_by(product_id=product_id, platform=platform, account_key="default").first()


def _sync_orders(db, product_map: dict[int, OSProduct], variant_map: dict[int, OSProductVariant]) -> tuple[int, int]:
    orders_changed = items_changed = 0
    status_map = {
        "new": "new", "fulfilling": "fulfilling", "shipped": "shipped",
        "completed": "completed", "cancelled": "cancelled",
    }
    for legacy in db.query(PlatformOrder).all():
        order = db.query(OSSalesOrder).filter_by(
            platform=legacy.platform,
            account_key="default",
            external_order_id=str(legacy.platform_order_id),
        ).first()
        if not order:
            order = OSSalesOrder(
                platform=legacy.platform,
                account_key="default",
                external_order_id=str(legacy.platform_order_id),
                status=status_map.get(legacy.status, "new"),
                buyer_name=legacy.buyer_name or "",
                receiver_name=legacy.receiver_name or "",
                receiver_phone=legacy.receiver_phone or "",
                shipping_address=legacy.shipping_address or "",
                shipping_message=legacy.shipping_message or "",
                ordered_at=legacy.ordered_at,
            )
            db.add(order)
            db.flush()
            orders_changed += 1

        os_product = product_map.get(legacy.product_id or -1)
        variant = variant_map.get(legacy.product_id or -1)
        listing = _find_os_listing(db, legacy.platform, os_product.id if os_product else None)
        external_item_id = str(
            legacy.platform_item_id or legacy.vendor_item_id or legacy.origin_product_no or legacy.id
        )
        item = db.query(OSSalesOrderItem).filter_by(order_id=order.id, external_item_id=external_item_id).first()
        if not item:
            item = OSSalesOrderItem(
                order_id=order.id,
                external_item_id=external_item_id,
                product_id=os_product.id if os_product else None,
                variant_id=variant.id if variant else None,
                listing_id=listing.id if listing else None,
                product_name=legacy.product_name or (os_product.name if os_product else ""),
                quantity=max(1, int(legacy.quantity or 1)),
                unit_sale_price_krw=int(round(float(legacy.unit_price or 0))),
                status="exception" if not os_product else "ordered" if legacy.supplier_order_id else "ready",
                exception_code="UNLINKED_PRODUCT" if not os_product else "",
            )
            db.add(item)
            db.flush()
            items_changed += 1
        else:
            item.product_id = os_product.id if os_product else None
            item.variant_id = variant.id if variant else None
            item.listing_id = listing.id if listing else None

        if os_product:
            supplier = _supplier(db, legacy.supplier or "") if legacy.supplier else None
            offer = None
            if supplier:
                offer = db.query(OSSupplierOffer).filter_by(supplier_id=supplier.id, product_id=os_product.id).first()
                if offer:
                    item.supplier_offer_id = offer.id
            if legacy.supplier_order_id or legacy.tracking_number:
                fulfillment = db.query(OSFulfillment).filter_by(order_item_id=item.id).first()
                if not fulfillment:
                    fulfillment = OSFulfillment(
                        order_item_id=item.id,
                        supplier_offer_id=offer.id if offer else None,
                        supplier_code=legacy.supplier or "",
                        supplier_order_id=legacy.supplier_order_id or "",
                        status="shipped" if legacy.tracking_number else "ordered",
                        quantity=item.quantity,
                        delivery_company=legacy.delivery_company or "",
                        tracking_number=legacy.tracking_number or "",
                        invoice_registered=bool(legacy.invoice_registered),
                        ordered_at=legacy.fulfilled_at,
                        shipped_at=legacy.shipped_at,
                    )
                    db.add(fulfillment)
                else:
                    fulfillment.supplier_order_id = legacy.supplier_order_id or fulfillment.supplier_order_id
                    fulfillment.delivery_company = legacy.delivery_company or fulfillment.delivery_company
                    fulfillment.tracking_number = legacy.tracking_number or fulfillment.tracking_number
                    fulfillment.invoice_registered = bool(legacy.invoice_registered)
    return orders_changed, items_changed


def _sync_financials(db, product_map: dict[int, OSProduct]) -> int:
    changed = 0
    for legacy in db.query(Order).all():
        order = db.query(OSSalesOrder).filter_by(
            platform=legacy.platform,
            account_key="default",
            external_order_id=str(legacy.platform_order_id or ""),
        ).first()
        if not order:
            continue
        os_product = product_map.get(legacy.product_id)
        item_q = db.query(OSSalesOrderItem).filter_by(order_id=order.id)
        if os_product:
            item_q = item_q.filter(OSSalesOrderItem.product_id == os_product.id)
        item = item_q.order_by(OSSalesOrderItem.id.asc()).first()
        if not item:
            continue
        line = db.query(OSSettlementLine).filter_by(order_item_id=item.id).first()
        values = {
            "gross_revenue_krw": int(round(float(legacy.gross_revenue or 0))),
            "supply_cost_krw": int(round(float(legacy.supply_cost or 0))),
            "platform_fee_krw": int(round(float(legacy.platform_fee or 0))),
            "shipping_cost_krw": int(round(float(legacy.net_shipping_cost or 0))),
            "ad_cost_krw": int(round(float(legacy.ad_cost or 0))),
            "return_cost_krw": int(round(float(legacy.return_cost or 0))),
            "tax_cost_krw": int(round(float(legacy.vat_payable or 0))),
            "net_profit_krw": int(round(float(legacy.net_profit or 0))),
            "status": "settled" if legacy.settled_at else "provisional",
            "settled_at": legacy.settled_at,
        }
        if not line:
            line = OSSettlementLine(order_item_id=item.id, platform=legacy.platform, **values)
            db.add(line)
            changed += 1
        else:
            for key, value in values.items():
                setattr(line, key, value)
    return changed


def migrate_legacy_to_os() -> dict[str, Any]:
    """Reconcile all currently supported legacy operational data into v3."""
    ensure_os_schema()
    with get_db() as db:
        product_map, variant_map = _product_maps(db)
        offers = _sync_offers(db, product_map, variant_map)
        listings, _ = _sync_listings(db, product_map, variant_map)
        orders, order_items = _sync_orders(db, product_map, variant_map)
        settlements = _sync_financials(db, product_map)
        db.commit()
        return {
            "ok": True,
            "products": len(product_map),
            "variants": len(variant_map),
            "new_offers": offers,
            "new_listings": listings,
            "new_orders": orders,
            "new_order_items": order_items,
            "new_settlements": settlements,
            "synced_at": datetime.utcnow().isoformat(),
        }
