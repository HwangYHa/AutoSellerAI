"""PlayAuto-style seller operations layer for AutoSellerAI.

This module adds human-operable metadata and safety policies on top of the existing
canonical Seller OS. It does not bypass marketplace/supplier mutation approvals.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

from app.db import get_db
from app.os.commerce_ops import get_commerce_ops_dashboard
from app.os.commerce_ops_models import OSChannelTemplate, OSInventoryPolicy, OSOrderWorkMeta
from app.os.models import OSProduct, OSSettlementLine, OSSupplierOffer
from app.os.schema import ensure_os_schema


def save_order_work_meta(
    order_item_id: int,
    *,
    user_tag: str = "",
    owner: str = "",
    priority: int = 50,
    cs_memo: str = "",
    gift_note: str = "",
    checked: bool = False,
) -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        row = db.query(OSOrderWorkMeta).filter_by(order_item_id=int(order_item_id)).first()
        if not row:
            row = OSOrderWorkMeta(order_item_id=int(order_item_id))
            db.add(row)
        row.user_tag = str(user_tag or "")[:120]
        row.owner = str(owner or "")[:120]
        row.priority = max(0, min(999, int(priority)))
        row.cs_memo = str(cs_memo or "")[:5000]
        row.gift_note = str(gift_note or "")[:400]
        row.checked = bool(checked)
        row.last_checked_at = datetime.utcnow() if checked else row.last_checked_at
        db.commit()
        return {"ok": True, "order_item_id": int(order_item_id), "meta_id": row.id}


def save_inventory_policy(
    product_id: int,
    *,
    safety_stock: int = 0,
    reserved_qty: int = 0,
    auto_soldout: bool = True,
    sellable: bool = True,
    note: str = "",
) -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        product = db.query(OSProduct).filter_by(id=int(product_id)).first()
        if not product:
            return {"ok": False, "error": "상품을 찾을 수 없습니다."}
        row = db.query(OSInventoryPolicy).filter_by(product_id=product.id).first()
        if not row:
            row = OSInventoryPolicy(product_id=product.id)
            db.add(row)
        row.safety_stock = max(0, int(safety_stock))
        row.reserved_qty = max(0, int(reserved_qty))
        row.auto_soldout = bool(auto_soldout)
        row.sellable = bool(sellable)
        row.note = str(note or "")[:500]
        db.commit()
        return {"ok": True, "product_id": product.id, "policy_id": row.id}


def save_channel_template(
    *,
    platform: str,
    name: str,
    category_hint: str = "",
    values: dict[str, Any] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    ensure_os_schema()
    platform = str(platform or "").strip().lower()
    name = str(name or "").strip()
    if platform not in {"coupang", "smartstore"}:
        return {"ok": False, "error": "지원 판매채널은 coupang, smartstore 입니다."}
    if not name:
        return {"ok": False, "error": "템플릿 이름이 필요합니다."}
    with get_db() as db:
        row = db.query(OSChannelTemplate).filter_by(platform=platform, name=name).first()
        if not row:
            row = OSChannelTemplate(platform=platform, name=name)
            db.add(row)
        row.category_hint = str(category_hint or "")[:240]
        row.template_json = json.dumps(values or {}, ensure_ascii=False, default=str)
        row.enabled = bool(enabled)
        db.commit()
        return {"ok": True, "template_id": row.id}


def _inventory_rows(db) -> list[dict[str, Any]]:
    products = db.query(OSProduct).filter(OSProduct.status != "archived").order_by(OSProduct.updated_at.desc()).limit(1000).all()
    policies = {x.product_id: x for x in db.query(OSInventoryPolicy).all()}
    rows: list[dict[str, Any]] = []
    for product in products:
        offers = db.query(OSSupplierOffer).filter_by(product_id=product.id, status="active").all()
        known_stocks = [int(x.stock_qty) for x in offers if x.stock_qty is not None]
        available_stock = max(known_stocks) if known_stocks else None
        policy = policies.get(product.id)
        safety = int(policy.safety_stock if policy else 0)
        reserved = int(policy.reserved_qty if policy else 0)
        threshold = safety + reserved
        stock_unknown = available_stock is None
        soldout_candidate = bool(
            policy
            and policy.auto_soldout
            and policy.sellable
            and available_stock is not None
            and available_stock <= threshold
        )
        rows.append({
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "status": product.status,
            "supplier_offers": len(offers),
            "available_stock": available_stock,
            "safety_stock": safety,
            "reserved_qty": reserved,
            "effective_available": None if available_stock is None else max(0, available_stock - reserved),
            "auto_soldout": bool(policy.auto_soldout) if policy else False,
            "sellable": bool(policy.sellable) if policy else True,
            "stock_unknown": stock_unknown,
            "soldout_candidate": soldout_candidate,
            "note": policy.note if policy else "",
        })
    return rows


def _settlement_calendar(db, days: int = 31) -> list[dict[str, Any]]:
    since = datetime.utcnow() - timedelta(days=max(1, int(days)))
    rows = db.query(OSSettlementLine).filter(OSSettlementLine.created_at >= since).all()
    by_day: dict[str, dict[str, int]] = {}
    for row in rows:
        dt = row.settled_at or row.created_at
        key = dt.strftime("%Y-%m-%d") if dt else "unknown"
        bucket = by_day.setdefault(key, {"orders": 0, "revenue_krw": 0, "profit_krw": 0, "settled": 0})
        bucket["orders"] += 1
        bucket["revenue_krw"] += int(row.gross_revenue_krw or 0)
        bucket["profit_krw"] += int(row.net_profit_krw or 0)
        bucket["settled"] += int(row.status == "settled")
    return [{"date": day, **values} for day, values in sorted(by_day.items(), reverse=True)]


def get_seller_tool_dashboard(limit: int = 500) -> dict[str, Any]:
    """Unified read model for multi-channel operations, inventory and settlement."""
    ensure_os_schema()
    base = get_commerce_ops_dashboard(limit=limit)
    with get_db() as db:
        metas = {x.order_item_id: x for x in db.query(OSOrderWorkMeta).all()}
        for row in base["rows"]:
            meta = metas.get(int(row["order_item_id"]))
            row.update({
                "user_tag": meta.user_tag if meta else "",
                "owner": meta.owner if meta else "",
                "priority": int(meta.priority) if meta else 50,
                "cs_memo": meta.cs_memo if meta else "",
                "gift_note": meta.gift_note if meta else "",
                "checked": bool(meta.checked) if meta else False,
                "last_checked_at": meta.last_checked_at if meta else None,
            })
        inventory = _inventory_rows(db)
        templates = db.query(OSChannelTemplate).order_by(OSChannelTemplate.platform, OSChannelTemplate.name).all()
        settlement = _settlement_calendar(db)

    inv_metrics = {
        "products": len(inventory),
        "stock_unknown": sum(1 for x in inventory if x["stock_unknown"]),
        "soldout_candidates": sum(1 for x in inventory if x["soldout_candidate"]),
        "auto_soldout_enabled": sum(1 for x in inventory if x["auto_soldout"]),
    }
    return {
        **base,
        "inventory": inventory,
        "inventory_metrics": inv_metrics,
        "templates": [
            {
                "id": x.id,
                "platform": x.platform,
                "name": x.name,
                "category_hint": x.category_hint,
                "values": json.loads(x.template_json or "{}"),
                "enabled": x.enabled,
            }
            for x in templates
        ],
        "settlement_calendar": settlement,
    }
