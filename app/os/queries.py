"""Seller OS detail read models.

The UI reads through this module instead of issuing ORM queries itself.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func

from app.db import get_db
from app.os.models import (
    OSAuditEvent,
    OSBackgroundTask,
    OSFulfillment,
    OSListing,
    OSListingVariant,
    OSOperationExecution,
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


def get_product_detail(product_id: int) -> dict[str, Any] | None:
    ensure_os_schema()
    with get_db() as db:
        p = db.query(OSProduct).filter_by(id=int(product_id)).first()
        if not p:
            return None
        variants = db.query(OSProductVariant).filter_by(product_id=p.id).order_by(OSProductVariant.id).all()
        offers = db.query(OSSupplierOffer).filter_by(product_id=p.id).order_by(OSSupplierOffer.supply_price_krw).all()
        suppliers = {
            s.id: s for s in db.query(OSSupplier).filter(OSSupplier.id.in_([o.supplier_id for o in offers] or [-1])).all()
        }
        listings = db.query(OSListing).filter_by(product_id=p.id).order_by(OSListing.platform).all()
        listing_rows = []
        for listing in listings:
            lv = db.query(OSListingVariant).filter_by(listing_id=listing.id).all()
            listing_rows.append({
                "id": listing.id,
                "platform": listing.platform,
                "external_product_id": listing.external_product_id or "",
                "status": listing.status,
                "sale_price_krw": listing.sale_price_krw,
                "title": listing.title,
                "error": listing.error,
                "items": [
                    {
                        "id": x.id,
                        "variant_id": x.variant_id,
                        "external_item_id": x.external_item_id,
                        "price_krw": x.sale_price_krw,
                        "stock_qty": x.stock_qty,
                        "status": x.status,
                    }
                    for x in lv
                ],
            })
        return {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "brand": p.brand,
            "category": p.category,
            "origin": p.origin,
            "material": p.material,
            "status": p.status,
            "product_type": p.product_type,
            "content": _loads(p.content_json, {}),
            "variants": [
                {
                    "id": x.id,
                    "sku": x.sku,
                    "option_key": x.option_key,
                    "option": _loads(x.option_json, {}),
                    "barcode": x.barcode,
                    "status": x.status,
                }
                for x in variants
            ],
            "offers": [
                {
                    "id": x.id,
                    "supplier": suppliers[x.supplier_id].name if x.supplier_id in suppliers else str(x.supplier_id),
                    "supplier_code": suppliers[x.supplier_id].code if x.supplier_id in suppliers else "",
                    "supplier_product_id": x.supplier_product_id,
                    "supplier_variant_id": x.supplier_variant_id,
                    "variant_id": x.variant_id,
                    "supply_price_krw": x.supply_price_krw,
                    "shipping_fee_krw": x.shipping_fee_krw,
                    "stock_qty": x.stock_qty,
                    "moq": x.moq,
                    "lead_time_days": x.lead_time_days,
                    "status": x.status,
                    "last_synced_at": x.last_synced_at,
                }
                for x in offers
            ],
            "listings": listing_rows,
            "updated_at": p.updated_at,
        }


def get_order_detail(order_id: int) -> dict[str, Any] | None:
    ensure_os_schema()
    with get_db() as db:
        order = db.query(OSSalesOrder).filter_by(id=int(order_id)).first()
        if not order:
            return None
        items = db.query(OSSalesOrderItem).filter_by(order_id=order.id).order_by(OSSalesOrderItem.id).all()
        result_items = []
        for item in items:
            fulfillment = db.query(OSFulfillment).filter_by(order_item_id=item.id).first()
            settlement = db.query(OSSettlementLine).filter_by(order_item_id=item.id).first()
            result_items.append({
                "id": item.id,
                "external_item_id": item.external_item_id,
                "product_id": item.product_id,
                "variant_id": item.variant_id,
                "listing_id": item.listing_id,
                "supplier_offer_id": item.supplier_offer_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_sale_price_krw": item.unit_sale_price_krw,
                "status": item.status,
                "exception_code": item.exception_code,
                "fulfillment": None if not fulfillment else {
                    "id": fulfillment.id,
                    "supplier_code": fulfillment.supplier_code,
                    "supplier_order_id": fulfillment.supplier_order_id,
                    "status": fulfillment.status,
                    "supply_cost_krw": fulfillment.supply_cost_krw,
                    "shipping_cost_krw": fulfillment.shipping_cost_krw,
                    "delivery_company": fulfillment.delivery_company,
                    "tracking_number": fulfillment.tracking_number,
                    "invoice_registered": fulfillment.invoice_registered,
                    "failure_code": fulfillment.failure_code,
                    "failure_message": fulfillment.failure_message,
                },
                "settlement": None if not settlement else {
                    "status": settlement.status,
                    "gross_revenue_krw": settlement.gross_revenue_krw,
                    "supply_cost_krw": settlement.supply_cost_krw,
                    "platform_fee_krw": settlement.platform_fee_krw,
                    "shipping_cost_krw": settlement.shipping_cost_krw,
                    "ad_cost_krw": settlement.ad_cost_krw,
                    "return_cost_krw": settlement.return_cost_krw,
                    "tax_cost_krw": settlement.tax_cost_krw,
                    "net_profit_krw": settlement.net_profit_krw,
                },
            })
        return {
            "id": order.id,
            "platform": order.platform,
            "order_no": order.external_order_id,
            "status": order.status,
            "buyer_name": order.buyer_name,
            "receiver_name": order.receiver_name,
            "receiver_phone": order.receiver_phone,
            "shipping_address": order.shipping_address,
            "shipping_message": order.shipping_message,
            "ordered_at": order.ordered_at,
            "items": result_items,
        }


def get_profit_summary() -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        sums = {
            "gross_revenue_krw": int(db.query(func.coalesce(func.sum(OSSettlementLine.gross_revenue_krw), 0)).scalar() or 0),
            "supply_cost_krw": int(db.query(func.coalesce(func.sum(OSSettlementLine.supply_cost_krw), 0)).scalar() or 0),
            "platform_fee_krw": int(db.query(func.coalesce(func.sum(OSSettlementLine.platform_fee_krw), 0)).scalar() or 0),
            "shipping_cost_krw": int(db.query(func.coalesce(func.sum(OSSettlementLine.shipping_cost_krw), 0)).scalar() or 0),
            "ad_cost_krw": int(db.query(func.coalesce(func.sum(OSSettlementLine.ad_cost_krw), 0)).scalar() or 0),
            "return_cost_krw": int(db.query(func.coalesce(func.sum(OSSettlementLine.return_cost_krw), 0)).scalar() or 0),
            "tax_cost_krw": int(db.query(func.coalesce(func.sum(OSSettlementLine.tax_cost_krw), 0)).scalar() or 0),
            "net_profit_krw": int(db.query(func.coalesce(func.sum(OSSettlementLine.net_profit_krw), 0)).scalar() or 0),
        }
        sums["settled_items"] = db.query(OSSettlementLine).filter_by(status="settled").count()
        sums["total_items"] = db.query(OSSettlementLine).count()
        revenue = sums["gross_revenue_krw"]
        sums["margin_pct"] = round(sums["net_profit_krw"] / revenue * 100, 2) if revenue else 0.0

        by_platform = []
        for platform in ("coupang", "smartstore"):
            rev = int(db.query(func.coalesce(func.sum(OSSettlementLine.gross_revenue_krw), 0)).filter(OSSettlementLine.platform == platform).scalar() or 0)
            profit = int(db.query(func.coalesce(func.sum(OSSettlementLine.net_profit_krw), 0)).filter(OSSettlementLine.platform == platform).scalar() or 0)
            count = db.query(OSSettlementLine).filter_by(platform=platform).count()
            by_platform.append({"platform": platform, "orders": count, "revenue_krw": rev, "profit_krw": profit})

        recent = db.query(OSSettlementLine).order_by(OSSettlementLine.id.desc()).limit(100).all()
        return {
            "summary": sums,
            "by_platform": by_platform,
            "recent": [
                {
                    "id": x.id,
                    "order_item_id": x.order_item_id,
                    "platform": x.platform,
                    "status": x.status,
                    "revenue_krw": x.gross_revenue_krw,
                    "supply_cost_krw": x.supply_cost_krw,
                    "fee_krw": x.platform_fee_krw,
                    "shipping_krw": x.shipping_cost_krw,
                    "ad_krw": x.ad_cost_krw,
                    "return_krw": x.return_cost_krw,
                    "tax_krw": x.tax_cost_krw,
                    "profit_krw": x.net_profit_krw,
                    "settled_at": x.settled_at,
                }
                for x in recent
            ],
        }


def get_operations_summary(limit: int = 50) -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        ops = db.query(OSOperationExecution).order_by(OSOperationExecution.id.desc()).limit(max(1, int(limit))).all()
        tasks = db.query(OSBackgroundTask).order_by(OSBackgroundTask.id.desc()).limit(max(1, int(limit))).all()
        audits = db.query(OSAuditEvent).order_by(OSAuditEvent.id.desc()).limit(max(1, int(limit))).all()
        return {
            "operations": [
                {
                    "id": x.id,
                    "action": x.action_type,
                    "entity": f"{x.entity_type}:{x.entity_id}",
                    "status": x.status,
                    "error": x.error,
                    "created_at": x.created_at,
                    "finished_at": x.finished_at,
                }
                for x in ops
            ],
            "tasks": [
                {
                    "id": x.id,
                    "type": x.task_type,
                    "queue": x.queue_name,
                    "status": x.status,
                    "progress": x.progress_pct,
                    "error": x.error,
                    "created_at": x.created_at,
                }
                for x in tasks
            ],
            "audit": [
                {
                    "id": x.id,
                    "actor": x.actor,
                    "action": x.action,
                    "entity": f"{x.entity_type}:{x.entity_id}",
                    "created_at": x.created_at,
                }
                for x in audits
            ],
        }
