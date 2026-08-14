"""Seller OS v3 supplier catalog ingestion.

New supplier integrations write the canonical Product/Variant/SupplierOffer spine
directly through this service. Legacy NormalizedProduct remains a compatibility
contract and is not the target for new integrations.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from app.db import get_db
from app.os.catalog_contracts import SupplierCatalogItem, SupplierCatalogVariant
from app.os.models import OSProduct, OSProductVariant, OSSupplier, OSSupplierOffer
from app.os.schema import ensure_os_schema


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _token(value: str, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return cleaned[:max_len] or "item"


def _stable_sku(prefix: str, *parts: str, max_len: int = 140) -> str:
    raw = "|".join(str(x or "") for x in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    readable = "-".join(_token(x, 28) for x in parts if str(x or "").strip())
    value = f"{prefix}-{readable}-{digest}" if readable else f"{prefix}-{digest}"
    return value[:max_len]


def _ensure_supplier(db, code: str) -> OSSupplier:
    code = str(code or "").strip().lower()
    row = db.query(OSSupplier).filter_by(code=code).first()
    if row:
        return row
    row = OSSupplier(code=code, name=code, enabled=True, connection_status="unknown")
    db.add(row); db.flush()
    return row


def _resolve_product(db, supplier: OSSupplier, item: SupplierCatalogItem, product_id: int | None) -> OSProduct:
    if product_id:
        row = db.query(OSProduct).filter_by(id=int(product_id)).first()
        if not row:
            raise ValueError("연결 대상 Product를 찾을 수 없습니다.")
        return row

    existing_offer = (
        db.query(OSSupplierOffer)
        .filter_by(supplier_id=supplier.id, supplier_product_id=item.supplier_product_id)
        .order_by(OSSupplierOffer.id.asc())
        .first()
    )
    if existing_offer:
        row = db.query(OSProduct).filter_by(id=existing_offer.product_id).first()
        if row:
            return row

    sku = _stable_sku("SUP", item.supplier_code, item.supplier_product_id)
    row = db.query(OSProduct).filter_by(sku=sku).first()
    if row:
        return row
    quality = item.data_quality_errors()
    row = OSProduct(
        sku=sku,
        name=item.name.strip(),
        brand=item.brand.strip(),
        category=item.category.strip(),
        origin=item.origin.strip(),
        material=item.material.strip(),
        status="review" if quality else "ready",
        product_type="dropship",
        content_json=_json({
            "images": list(item.images),
            "detail_images": list(item.detail_images),
            "detail_html": item.detail_html,
            "supplier_origin": {
                "supplier_code": item.supplier_code,
                "supplier_product_id": item.supplier_product_id,
                "source_url": item.source_url,
            },
            "data_quality_errors": quality,
        }),
    )
    db.add(row); db.flush()
    return row


def _upsert_variant(db, product: OSProduct, item: SupplierCatalogItem, variant: SupplierCatalogVariant) -> OSProductVariant:
    option_key = variant.option_key or "__default__"
    row = db.query(OSProductVariant).filter_by(product_id=product.id, option_key=option_key).first()
    if not row:
        row = OSProductVariant(
            product_id=product.id,
            sku=_stable_sku("VAR", product.sku, variant.supplier_variant_id or option_key, max_len=180),
            option_key=option_key,
            option_json=_json(variant.option_values),
            barcode=variant.barcode or "",
            status=variant.status or "active",
        )
        db.add(row); db.flush()
    else:
        row.option_json = _json(variant.option_values)
        row.barcode = variant.barcode or row.barcode or ""
        row.status = variant.status or row.status
    return row


def ingest_supplier_catalog_item(item: SupplierCatalogItem, *, product_id: int | None = None) -> dict[str, Any]:
    """Idempotently write one supplier item to canonical v3 tables.

    ``product_id`` is supplied only when the caller has positively matched this
    supplier item to an existing master Product. Automatic cross-supplier merging is
    intentionally avoided because a false match can send the wrong item to a buyer.
    """
    ensure_os_schema()
    structural = [x for x in item.data_quality_errors() if x in {
        "SUPPLIER_REQUIRED", "SUPPLIER_PRODUCT_ID_REQUIRED", "PRODUCT_NAME_REQUIRED"
    }]
    if structural:
        return {"ok": False, "error": ", ".join(structural)}

    with get_db() as db:
        supplier = _ensure_supplier(db, item.supplier_code)
        product = _resolve_product(db, supplier, item, product_id)
        quality = item.data_quality_errors()

        product.name = item.name.strip() or product.name
        product.brand = item.brand.strip()
        product.category = item.category.strip()
        product.origin = item.origin.strip()
        product.material = item.material.strip()
        if product.status in {"draft", "review", "ready"}:
            product.status = "review" if quality else "ready"
        content = {
            "images": list(item.images),
            "detail_images": list(item.detail_images),
            "detail_html": item.detail_html,
            "supplier_origin": {
                "supplier_code": item.supplier_code,
                "supplier_product_id": item.supplier_product_id,
                "source_url": item.source_url,
            },
            "data_quality_errors": quality,
        }
        product.content_json = _json(content)

        offer_ids: list[int] = []
        variant_ids: list[int] = []
        effective_variants = item.effective_variants()
        for variant in effective_variants:
            internal_variant = _upsert_variant(db, product, item, variant)
            variant_ids.append(internal_variant.id)
            supplier_variant_id = variant.supplier_variant_id or "__default__"
            offer = db.query(OSSupplierOffer).filter_by(
                supplier_id=supplier.id,
                supplier_product_id=item.supplier_product_id,
                supplier_variant_id=supplier_variant_id,
            ).first()
            if not offer:
                offer = OSSupplierOffer(
                    supplier_id=supplier.id,
                    product_id=product.id,
                    variant_id=internal_variant.id,
                    supplier_product_id=item.supplier_product_id,
                    supplier_variant_id=supplier_variant_id,
                )
                db.add(offer); db.flush()
            offer.product_id = product.id
            offer.variant_id = internal_variant.id
            offer.source_url = item.source_url
            offer.supply_price_krw = int(variant.supply_price_krw or 0)
            offer.shipping_fee_krw = int(item.shipping_fee_krw or 0)
            offer.stock_qty = None if variant.stock_qty is None else int(variant.stock_qty)
            offer.moq = max(1, int(item.moq or 1))
            offer.lead_time_days = max(0, int(item.lead_time_days or 0))
            offer.status = variant.status or "active"
            offer.raw_json = _json({"item": item.raw, "variant": variant.raw})
            offer.last_synced_at = datetime.utcnow()
            offer_ids.append(offer.id)

        # Retire supplier variants that disappeared instead of deleting historical IDs.
        active_supplier_variant_ids = {v.supplier_variant_id or "__default__" for v in effective_variants}
        old_offers = db.query(OSSupplierOffer).filter_by(
            supplier_id=supplier.id,
            supplier_product_id=item.supplier_product_id,
        ).all()
        for old in old_offers:
            if old.supplier_variant_id not in active_supplier_variant_ids:
                old.status = "inactive"

        db.commit()
        return {
            "ok": True,
            "product_id": product.id,
            "variant_ids": variant_ids,
            "offer_ids": offer_ids,
            "status": product.status,
            "data_quality_errors": quality,
        }
