"""PlayAuto-inspired commerce operations domain models.

These tables add operational controls that sit above marketplace/supplier adapters:
product matching rules, claims, shipment controls, order work metadata, inventory
safety policies and reusable marketplace templates.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class OSProductMatchRule(Base):
    __tablename__ = "os_product_match_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    external_product_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    external_item_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("os_products.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("os_product_variants.id", ondelete="SET NULL"), nullable=True, index=True)
    supplier_offer_id: Mapped[int | None] = mapped_column(ForeignKey("os_supplier_offers.id", ondelete="SET NULL"), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    note: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("platform", "external_item_id", name="uq_os_match_rule_platform_item"),)


class OSOrderClaim(Base):
    __tablename__ = "os_order_claims"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    external_claim_id: Mapped[str] = mapped_column(String(220), index=True)
    external_order_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    external_item_id: Mapped[str] = mapped_column(String(220), default="", index=True)
    claim_type: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="requested", index=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("platform", "external_claim_id", name="uq_os_claim_platform_external"),)


class OSOrderOpsState(Base):
    __tablename__ = "os_order_ops_states"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("os_sales_order_items.id", ondelete="CASCADE"), unique=True, index=True)
    shipment_hold: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    hold_reason: Mapped[str] = mapped_column(String(500), default="")
    shipment_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    delay_notified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    claim_blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    operator_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class OSOrderWorkMeta(Base):
    __tablename__ = "os_order_work_meta"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("os_sales_order_items.id", ondelete="CASCADE"), unique=True, index=True)
    user_tag: Mapped[str] = mapped_column(String(120), default="", index=True)
    owner: Mapped[str] = mapped_column(String(120), default="", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50, index=True)
    cs_memo: Mapped[str] = mapped_column(Text, default="")
    gift_note: Mapped[str] = mapped_column(String(400), default="")
    checked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class OSInventoryPolicy(Base):
    __tablename__ = "os_inventory_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("os_products.id", ondelete="CASCADE"), unique=True, index=True)
    safety_stock: Mapped[int] = mapped_column(Integer, default=0)
    reserved_qty: Mapped[int] = mapped_column(Integer, default=0)
    auto_soldout: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sellable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class OSChannelTemplate(Base):
    __tablename__ = "os_channel_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    category_hint: Mapped[str] = mapped_column(String(240), default="")
    template_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("platform", "name", name="uq_os_channel_template_platform_name"),)
