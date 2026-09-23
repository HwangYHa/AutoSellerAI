from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, _get_engine


class PricingPolicy(Base):
    __tablename__ = "pricing_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), default="default", unique=True)
    target_margin_rate: Mapped[float] = mapped_column(Float, default=0.36)
    coupang_fallback_fee_rate: Mapped[float] = mapped_column(Float, default=0.108)
    smartstore_fallback_fee_rate: Mapped[float] = mapped_column(Float, default=0.06)
    rounding_unit: Mapped[int] = mapped_column(Integer, default=900)
    coupang_auto_down_pct: Mapped[float] = mapped_column(Float, default=5.0)
    coupang_auto_up_pct: Mapped[float] = mapped_column(Float, default=8.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CategoryFeeRule(Base):
    __tablename__ = "category_fee_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    category_key: Mapped[str] = mapped_column(String(220), index=True)
    fee_rate: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    note: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("ix_fee_rule_platform_category", "platform", "category_key"),)


class PriceChangeLog(Base):
    __tablename__ = "price_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    listing_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    platform_id: Mapped[str] = mapped_column(String(200), default="")
    supply_price: Mapped[float] = mapped_column(Float, default=0.0)
    fee_rate: Mapped[float] = mapped_column(Float, default=0.0)
    target_margin_rate: Mapped[float] = mapped_column(Float, default=0.0)
    before_price: Mapped[float] = mapped_column(Float, default=0.0)
    after_price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)



class SupplierProductMap(Base):
    __tablename__ = "supplier_product_maps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    supplier_id: Mapped[str] = mapped_column(String(30), index=True)
    raw_id: Mapped[str] = mapped_column(String(200), index=True)
    match_type: Mapped[str] = mapped_column(String(40), default="direct")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    previous_supply_price: Mapped[float] = mapped_column(Float, default=0.0)
    current_supply_price: Mapped[float] = mapped_column(Float, default=0.0)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_supplier_map_supplier_raw", "supplier_id", "raw_id"),
    )


class SupplyPriceSnapshot(Base):
    __tablename__ = "supply_price_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    supplier_id: Mapped[str] = mapped_column(String(30), index=True)
    raw_id: Mapped[str] = mapped_column(String(200), default="")
    old_price: Mapped[float] = mapped_column(Float, default=0.0)
    new_price: Mapped[float] = mapped_column(Float, default=0.0)
    change_rate: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="ok", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PriceRiskSnapshot(Base):
    __tablename__ = "price_risk_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    listing_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    platform_id: Mapped[str] = mapped_column(String(200), default="")
    supply_price: Mapped[float] = mapped_column(Float, default=0.0)
    current_price: Mapped[float] = mapped_column(Float, default=0.0)
    fee_rate: Mapped[float] = mapped_column(Float, default=0.0)
    margin_rate: Mapped[float] = mapped_column(Float, default=0.0)
    target_margin_rate: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)



class PriceChangeBatch(Base):
    __tablename__ = "price_change_batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(30), default="selected")
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    sensitive_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PriceChangeBatchItem(Base):
    __tablename__ = "price_change_batch_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_key: Mapped[str] = mapped_column(String(64), index=True)
    price_change_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    listing_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    platform_id: Mapped[str] = mapped_column(String(200), default="")
    before_price: Mapped[float] = mapped_column(Float, default=0.0)
    after_price: Mapped[float] = mapped_column(Float, default=0.0)
    change_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sales_count: Mapped[int] = mapped_column(Integer, default=0)
    guard_level: Mapped[str] = mapped_column(String(30), default="NORMAL", index=True)
    guard_reason: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PriceRollbackLog(Base):
    __tablename__ = "price_rollback_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_change_log_id: Mapped[int] = mapped_column(Integer, index=True)
    source_batch_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    listing_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    platform_id: Mapped[str] = mapped_column(String(200), default="")
    from_price: Mapped[float] = mapped_column(Float, default=0.0)
    restored_price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


def ensure_pricing_schema() -> None:
    PricingPolicy.__table__.create(bind=_get_engine(), checkfirst=True)
    CategoryFeeRule.__table__.create(bind=_get_engine(), checkfirst=True)
    PriceChangeLog.__table__.create(bind=_get_engine(), checkfirst=True)
    SupplierProductMap.__table__.create(bind=_get_engine(), checkfirst=True)
    SupplyPriceSnapshot.__table__.create(bind=_get_engine(), checkfirst=True)
    PriceRiskSnapshot.__table__.create(bind=_get_engine(), checkfirst=True)
    PriceChangeBatch.__table__.create(bind=_get_engine(), checkfirst=True)
    PriceChangeBatchItem.__table__.create(bind=_get_engine(), checkfirst=True)
    PriceRollbackLog.__table__.create(bind=_get_engine(), checkfirst=True)
