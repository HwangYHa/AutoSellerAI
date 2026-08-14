"""Strict supplier catalog contracts for Seller OS v3.

Unknown commercial/compliance facts are represented as ``None``. V3 must never
invent origin, shipping fee, stock, lead time or brand-sale permission just to make
a product look complete.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SupplierCatalogVariant:
    supplier_variant_id: str
    option_key: str
    option_values: dict[str, str] = field(default_factory=dict)
    barcode: str = ""
    supply_price_krw: int | None = None
    stock_qty: int | None = None
    status: str = "active"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SupplierCatalogItem:
    supplier_code: str
    supplier_product_id: str
    name: str
    source_url: str = ""
    brand: str = ""
    category: str = ""
    origin: str = ""
    material: str = ""
    images: tuple[str, ...] = ()
    detail_images: tuple[str, ...] = ()
    detail_html: str = ""
    supply_price_krw: int | None = None
    stock_qty: int | None = None
    shipping_fee_krw: int | None = None
    moq: int | None = None
    lead_time_days: int | None = None
    # None = 아직 확인하지 못함. False/True는 공급계약/증빙으로 확인된 값만 사용.
    online_sale_allowed: bool | None = None
    authenticity_evidence_available: bool | None = None
    verification_source: str = ""
    verification_note: str = ""
    variants: tuple[SupplierCatalogVariant, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    def effective_variants(self) -> tuple[SupplierCatalogVariant, ...]:
        if self.variants:
            return self.variants
        return (
            SupplierCatalogVariant(
                supplier_variant_id="__default__",
                option_key="__default__",
                supply_price_krw=self.supply_price_krw,
                stock_qty=self.stock_qty,
            ),
        )

    def data_quality_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.supplier_code.strip():
            errors.append("SUPPLIER_REQUIRED")
        if not self.supplier_product_id.strip():
            errors.append("SUPPLIER_PRODUCT_ID_REQUIRED")
        if not self.name.strip():
            errors.append("PRODUCT_NAME_REQUIRED")
        for variant in self.effective_variants():
            if variant.supply_price_krw is None or int(variant.supply_price_krw) <= 0:
                errors.append(f"SUPPLY_PRICE_UNKNOWN:{variant.option_key}")
            if variant.stock_qty is None:
                errors.append(f"STOCK_UNKNOWN:{variant.option_key}")
        if self.shipping_fee_krw is None:
            errors.append("SHIPPING_FEE_UNKNOWN")
        if self.moq is None:
            errors.append("MOQ_UNKNOWN")
        return errors

    def compliance_unknowns(self) -> list[str]:
        errors: list[str] = []
        if self.online_sale_allowed is None:
            errors.append("ONLINE_SALE_PERMISSION_UNKNOWN")
        if self.authenticity_evidence_available is None:
            errors.append("AUTHENTICITY_EVIDENCE_UNKNOWN")
        return errors
