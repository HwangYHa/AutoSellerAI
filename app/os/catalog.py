"""Seller OS v3 supplier catalog ingestion.

New supplier integrations write the canonical Product/Variant/SupplierOffer spine
directly through this service. Unknown supplier facts remain explicitly unverified.
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
from app.os.quality_models import OSOfferVerification
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
    db.add(row)
    db.flush()
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
            "compliance_unknowns": item.compliance_unknowns(),
        }),
    )
    db.add(row)
    db.flush()
    return row


def _upsert_variant(db, product: OSProduct, variant: SupplierCatalogVariant) -> OSProductVariant:
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
        db.add(row)
        db.flush()
    else:
        row.option_json = _json(variant.option_values)
        row.barcode = variant.barcode or row.barcode or ""
        row.status = variant.status or row.status
    return row


def _upsert_offer_verification(
    db,
    *,
    offer: OSSupplierOffer,
    item: SupplierCatalogItem,
    variant: SupplierCatalogVariant,
    explicit_variants: bool,
) -> OSOfferVerification:
    row = db.query(OSOfferVerification).filter_by(offer_id=offer.id).first()
    if not row:
        row = OSOfferVerification(offer_id=offer.id)
        db.add(row)
        db.flush()

    supplier_variant_id = str(variant.supplier_variant_id or "").strip()
    variant_identity_verified = (
        bool(supplier_variant_id and supplier_variant_id != "__default__")
        if explicit_variants
        else True
    )
    row.price_known = variant.supply_price_krw is not None and int(variant.supply_price_krw) > 0
    row.shipping_fee_known = item.shipping_fee_krw is not None
    row.stock_known = variant.stock_qty is not None
    row.moq_known = item.moq is not None
    row.variant_identity_verified = variant_identity_verified
    row.online_sale_allowed = item.online_sale_allowed is True
    row.authenticity_evidence_available = item.authenticity_evidence_available is True
    row.verification_source = str(item.verification_source or "")[:80]
    row.note = str(item.verification_note or "")
    row.verified_at = datetime.utcnow()
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
        compliance_unknowns = item.compliance_unknowns()

        product.name = item.name.strip() or product.name
        product.brand = item.brand.strip()
        product.category = item.category.strip()
        product.origin = item.origin.strip()
        product.material = item.material.strip()
        if product.status in {"draft", "review", "ready"}:
            product.status = "review" if quality else "ready"
        product.content_json = _json({
            "images": list(item.images),
            "detail_images": list(item.detail_images),
            "detail_html": item.detail_html,
            "supplier_origin": {
                "supplier_code": item.supplier_code,
                "supplier_product_id": item.supplier_product_id,
                "source_url": item.source_url,
            },
            "data_quality_errors": quality,
            "compliance_unknowns": compliance_unknowns,
        })

        offer_ids: list[int] = []
        variant_ids: list[int] = []
        verification_ids: list[int] = []
        effective_variants = item.effective_variants()
        explicit_variants = bool(item.variants)
        for variant in effective_variants:
            internal_variant = _upsert_variant(db, product, variant)
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
                db.add(offer)
                db.flush()
            offer.product_id = product.id
            offer.variant_id = internal_variant.id
            offer.source_url = item.source_url
            # Numeric fallback is for schema compatibility only; verification keeps
            # unknown separate from a genuine 0/free value and blocks unsafe orders.
            offer.supply_price_krw = int(variant.supply_price_krw or 0)
            offer.shipping_fee_krw = int(item.shipping_fee_krw or 0)
            offer.stock_qty = None if variant.stock_qty is None else int(variant.stock_qty)
            offer.moq = max(1, int(item.moq or 1))
            offer.lead_time_days = max(0, int(item.lead_time_days or 0))
            offer.status = variant.status or "active"
            offer.raw_json = _json({"item": item.raw, "variant": variant.raw})
            offer.last_synced_at = datetime.utcnow()
            offer_ids.append(offer.id)

            verification = _upsert_offer_verification(
                db,
                offer=offer,
                item=item,
                variant=variant,
                explicit_variants=explicit_variants,
            )
            verification_ids.append(verification.id)

        active_supplier_variant_ids = {v.supplier_variant_id or "__default__" for v in effective_variants}
        old_offers = db.query(OSSupplierOffer).filter_by(
            supplier_id=supplier.id,
            supplier_product_id=item.supplier_product_id,
        ).all()
        for old in old_offers:
            if old.supplier_variant_id not in active_supplier_variant_ids:
                old.status = "inactive"

        product_id_value = int(product.id)
        status_value = str(product.status)
        db.commit()
        return {
            "ok": True,
            "product_id": product_id_value,
            "variant_ids": variant_ids,
            "offer_ids": offer_ids,
            "verification_ids": verification_ids,
            "status": status_value,
            "data_quality_errors": quality,
            "compliance_unknowns": compliance_unknowns,
        }
