from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, Index
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


def ensure_pricing_schema() -> None:
    PricingPolicy.__table__.create(bind=_get_engine(), checkfirst=True)
    CategoryFeeRule.__table__.create(bind=_get_engine(), checkfirst=True)
    PriceChangeLog.__table__.create(bind=_get_engine(), checkfirst=True)
