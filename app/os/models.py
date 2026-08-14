"""Canonical Seller OS v3 relational model.

This schema intentionally uses new ``os_*`` tables so the application can migrate
from the legacy schema without destructive in-place changes.  The v3 spine is:

Supplier -> Product/Variant -> SupplierOffer -> Listing/Variant ->
SalesOrder/Item -> Fulfillment -> SettlementLine -> LearningSignal

Every external side effect is additionally represented by ApprovalRequest and
OperationExecution.  Background work is represented by BackgroundTask.

Money is stored as integer KRW to avoid floating point accounting drift.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class OSSupplier(Base):
    __tablename__ = "os_suppliers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # search|detail|stock|order|cancel|tracking|dropship as JSON string list
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    connection_status: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class OSProduct(Base):
    __tablename__ = "os_products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(400))
    brand: Mapped[str] = mapped_column(String(160), default="", index=True)
    category: Mapped[str] = mapped_column(String(240), default="", index=True)
    origin: Mapped[str] = mapped_column(String(120), default="")
    material: Mapped[str] = mapped_column(String(240), default="")
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    # draft | review | ready | active | paused | archived
    product_type: Mapped[str] = mapped_column(String(30), default="dropship", index=True)
    # dropship | stocked
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class OSProductVariant(Base):
    __tablename__ = "os_product_variants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("os_products.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    option_key: Mapped[str] = mapped_column(String(300), default="")
    option_json: Mapped[str] = mapped_column(Text, default="{}")
    barcode: Mapped[str] = mapped_column(String(100), default="", index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("product_id", "option_key", name="uq_os_variant_product_option"),
    )


class OSSupplierOffer(Base):
    __tablename__ = "os_supplier_offers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("os_suppliers.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("os_products.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("os_product_variants.id", ondelete="CASCADE"), nullable=True, index=True)
    supplier_product_id: Mapped[str] = mapped_column(String(220), index=True)
    supplier_variant_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    supply_price_krw: Mapped[int] = mapped_column(Integer, default=0)
    shipping_fee_krw: Mapped[int] = mapped_column(Integer, default=0)
    stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    moq: Mapped[int] = mapped_column(Integer, default=1)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "supplier_product_id", "supplier_variant_id",
            name="uq_os_supplier_offer_identity",
        ),
        Index("ix_os_offer_product_status", "product_id", "status"),
    )


class OSListing(Base):
    __tablename__ = "os_listings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("os_products.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    account_key: Mapped[str] = mapped_column(String(80), default="default", index=True)
    external_product_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    # draft | pending_approval | publishing | active | paused | failed | archived
    sale_price_krw: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("product_id", "platform", "account_key", name="uq_os_listing_product_platform"),
        UniqueConstraint("platform", "account_key", "external_product_id", name="uq_os_listing_external"),
    )


class OSListingVariant(Base):
    __tablename__ = "os_listing_variants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("os_listings.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("os_product_variants.id", ondelete="SET NULL"), nullable=True, index=True)
    external_item_id: Mapped[str] = mapped_column(String(220), index=True)
    external_parent_item_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    sale_price_krw: Mapped[int] = mapped_column(Integer, default=0)
    stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("listing_id", "external_item_id", name="uq_os_listing_variant_external"),
    )


class OSSalesOrder(Base):
    __tablename__ = "os_sales_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    account_key: Mapped[str] = mapped_column(String(80), default="default", index=True)
    external_order_id: Mapped[str] = mapped_column(String(220), index=True)
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    # new | exception | ready_to_fulfill | fulfilling | shipped | completed | cancelled
    buyer_name: Mapped[str] = mapped_column(String(120), default="")
    receiver_name: Mapped[str] = mapped_column(String(120), default="")
    receiver_phone: Mapped[str] = mapped_column(String(80), default="")
    shipping_address: Mapped[str] = mapped_column(Text, default="")
    shipping_message: Mapped[str] = mapped_column(String(400), default="")
    ordered_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("platform", "account_key", "external_order_id", name="uq_os_sales_order_external"),
    )


class OSSalesOrderItem(Base):
    __tablename__ = "os_sales_order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("os_sales_orders.id", ondelete="CASCADE"), index=True)
    external_item_id: Mapped[str] = mapped_column(String(220), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("os_products.id", ondelete="SET NULL"), nullable=True, index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("os_product_variants.id", ondelete="SET NULL"), nullable=True, index=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("os_listings.id", ondelete="SET NULL"), nullable=True, index=True)
    supplier_offer_id: Mapped[int | None] = mapped_column(ForeignKey("os_supplier_offers.id", ondelete="SET NULL"), nullable=True, index=True)
    product_name: Mapped[str] = mapped_column(String(400), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_sale_price_krw: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    # new | exception | ready | approved | ordered | shipped | completed | cancelled
    exception_code: Mapped[str] = mapped_column(String(80), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("order_id", "external_item_id", name="uq_os_order_item_external"),
    )


class OSApprovalRequest(Base):
    __tablename__ = "os_approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    action_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    summary: Mapped[str] = mapped_column(String(500), default="")
    risk_level: Mapped[str] = mapped_column(String(20), default="high", index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    # pending | approved | rejected | consumed | expired | cancelled
    requested_by: Mapped[str] = mapped_column(String(120), default="system")
    decided_by: Mapped[str] = mapped_column(String(120), default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index("ix_os_approval_pending", "status", "risk_level", "requested_at"),
    )


class OSOperationExecution(Base):
    __tablename__ = "os_operation_executions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    action_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("os_approval_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    # pending | running | succeeded | failed | cancelled
    request_json: Mapped[str] = mapped_column(Text, default="{}")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class OSFulfillment(Base):
    __tablename__ = "os_fulfillments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("os_sales_order_items.id", ondelete="CASCADE"), unique=True, index=True)
    supplier_offer_id: Mapped[int | None] = mapped_column(ForeignKey("os_supplier_offers.id", ondelete="SET NULL"), nullable=True, index=True)
    supplier_code: Mapped[str] = mapped_column(String(50), default="", index=True)
    supplier_order_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval", index=True)
    # pending_approval | approved | ordering | ordered | shipping | shipped | completed | failed | cancelled
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    supply_cost_krw: Mapped[int] = mapped_column(Integer, default=0)
    shipping_cost_krw: Mapped[int] = mapped_column(Integer, default=0)
    delivery_company: Mapped[str] = mapped_column(String(80), default="")
    tracking_number: Mapped[str] = mapped_column(String(140), default="", index=True)
    invoice_registered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    failure_code: Mapped[str] = mapped_column(String(80), default="", index=True)
    failure_message: Mapped[str] = mapped_column(Text, default="")
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class OSSettlementLine(Base):
    __tablename__ = "os_settlement_lines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("os_sales_order_items.id", ondelete="CASCADE"), unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    gross_revenue_krw: Mapped[int] = mapped_column(Integer, default=0)
    supply_cost_krw: Mapped[int] = mapped_column(Integer, default=0)
    platform_fee_krw: Mapped[int] = mapped_column(Integer, default=0)
    shipping_cost_krw: Mapped[int] = mapped_column(Integer, default=0)
    ad_cost_krw: Mapped[int] = mapped_column(Integer, default=0)
    return_cost_krw: Mapped[int] = mapped_column(Integer, default=0)
    tax_cost_krw: Mapped[int] = mapped_column(Integer, default=0)
    net_profit_krw: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(30), default="estimated", index=True)
    # estimated | provisional | settled | adjusted
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class OSLearningSignal(Base):
    __tablename__ = "os_learning_signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("os_products.id", ondelete="CASCADE"), nullable=True, index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("os_product_variants.id", ondelete="CASCADE"), nullable=True, index=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("os_listings.id", ondelete="CASCADE"), nullable=True, index=True)
    signal_type: Mapped[str] = mapped_column(String(80), index=True)
    value_int: Mapped[int] = mapped_column(Integer, default=0)
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class OSBackgroundTask(Base):
    __tablename__ = "os_background_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    task_type: Mapped[str] = mapped_column(String(80), index=True)
    queue_name: Mapped[str] = mapped_column(String(40), default="default", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(180), default="", index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    # queued | running | succeeded | failed | cancelled
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class OSSyncCursor(Base):
    __tablename__ = "os_sync_cursors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(60), index=True)
    scope: Mapped[str] = mapped_column(String(100), index=True)
    cursor_value: Mapped[str] = mapped_column(Text, default="")
    watermark: Mapped[str] = mapped_column(String(120), default="")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("source", "scope", name="uq_os_sync_cursor_source_scope"),
    )


class OSAuditEvent(Base):
    __tablename__ = "os_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(120), default="system", index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), default="", index=True)
    entity_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
