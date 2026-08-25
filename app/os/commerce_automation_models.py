"""Persistent models for full commerce automation.

All tables are additive so existing SQLite installations can migrate safely through
SQLAlchemy create_all without ALTER TABLE operations.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class OSMarketplaceInquiry(Base):
    __tablename__ = "os_marketplace_inquiries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    inquiry_type: Mapped[str] = mapped_column(String(30), index=True)  # product | customer | callcenter
    external_inquiry_id: Mapped[str] = mapped_column(String(220), index=True)
    external_order_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    external_item_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("os_products.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    question: Mapped[str] = mapped_column(Text, default="")
    customer_name: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)  # open | drafted | answered | error
    answer: Mapped[str] = mapped_column(Text, default="")
    ai_draft: Mapped[str] = mapped_column(Text, default="")
    template_key: Mapped[str] = mapped_column(String(120), default="")
    requires_human: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    asked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("platform", "inquiry_type", "external_inquiry_id", name="uq_os_inquiry_external"),
        Index("ix_os_inquiry_work", "status", "requires_human", "asked_at"),
    )


class OSInquiryTemplate(Base):
    __tablename__ = "os_inquiry_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(40), default="all", index=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("platform", "key", name="uq_os_inquiry_template_platform_key"),)


class OSChannelSettlement(Base):
    __tablename__ = "os_channel_settlements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    external_key: Mapped[str] = mapped_column(String(240), index=True)
    external_order_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    external_item_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    settlement_type: Mapped[str] = mapped_column(String(40), default="sale", index=True)
    recognition_date: Mapped[str] = mapped_column(String(20), default="", index=True)
    settlement_date: Mapped[str] = mapped_column(String(20), default="", index=True)
    gross_revenue_krw: Mapped[int] = mapped_column(Integer, default=0)
    platform_fee_krw: Mapped[int] = mapped_column(Integer, default=0)
    shipping_amount_krw: Mapped[int] = mapped_column(Integer, default=0)
    settlement_amount_krw: Mapped[int] = mapped_column(Integer, default=0)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("platform", "external_key", name="uq_os_channel_settlement_external"),)


class OSSchedulerRule(Base):
    __tablename__ = "os_scheduler_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=5)
    queue_name: Mapped[str] = mapped_column(String(40), default="sync")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    description: Mapped[str] = mapped_column(String(400), default="")
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class OSPaymentSession(Base):
    __tablename__ = "os_payment_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fulfillment_id: Mapped[int] = mapped_column(ForeignKey("os_fulfillments.id", ondelete="CASCADE"), unique=True, index=True)
    supplier_code: Mapped[str] = mapped_column(String(50), default="", index=True)
    payment_mode: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    # api_auto | balance | corporate_credit | interactive_card | bank_transfer | unknown
    status: Mapped[str] = mapped_column(String(40), default="preparing", index=True)
    # preparing | awaiting_user | authorizing | paid | failed | expired | cancelled | refunded
    expected_amount_krw: Mapped[int] = mapped_column(Integer, default=0)
    actual_amount_krw: Mapped[int] = mapped_column(Integer, default=0)
    payment_url: Mapped[str] = mapped_column(Text, default="")
    external_payment_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    user_action_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class OSInventoryAutomationState(Base):
    """Hysteresis state for external sold-out/restock mutations.

    A single supplier timeout/zero response must never disable a marketplace listing.
    The automation therefore requires consecutive observations before mutating the
    external channel and remembers only states it changed itself.
    """

    __tablename__ = "os_inventory_automation_states"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("os_products.id", ondelete="CASCADE"), unique=True, index=True)
    low_stock_confirmations: Mapped[int] = mapped_column(Integer, default=0)
    restock_confirmations: Mapped[int] = mapped_column(Integer, default=0)
    auto_sold_out: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_observed_stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_action: Mapped[str] = mapped_column(String(40), default="", index=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
