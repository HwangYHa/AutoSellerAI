from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ContentProfitSnapshot(Base):
    """게시물/캠페인 수익성 스냅샷.

    조회/좋아요보다 실제 귀속 주문과 순이익을 우선하여 Content Score를 계산한다.
    scope_type: post | campaign
    """
    __tablename__ = "content_profit_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(20), index=True)  # post | campaign
    scope_key: Mapped[str] = mapped_column(String(200), index=True)
    post_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    threads_post_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    campaign_key: Mapped[str] = mapped_column(String(120), default="", index=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    content_angle: Mapped[str] = mapped_column(String(40), default="", index=True)

    clicks: Mapped[int] = mapped_column(Integer, default=0)
    attributed_orders: Mapped[int] = mapped_column(Integer, default=0)
    deterministic_orders: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_orders: Mapped[int] = mapped_column(Integer, default=0)
    returned_orders: Mapped[int] = mapped_column(Integer, default=0)

    gross_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    supply_cost: Mapped[float] = mapped_column(Float, default=0.0)
    platform_fee: Mapped[float] = mapped_column(Float, default=0.0)
    shipping_cost: Mapped[float] = mapped_column(Float, default=0.0)
    ad_cost: Mapped[float] = mapped_column(Float, default=0.0)
    return_cost: Mapped[float] = mapped_column(Float, default=0.0)
    vat_payable: Mapped[float] = mapped_column(Float, default=0.0)
    net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    net_margin_rate: Mapped[float] = mapped_column(Float, default=0.0)
    conversion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    return_rate: Mapped[float] = mapped_column(Float, default=0.0)
    profit_per_click: Mapped[float] = mapped_column(Float, default=0.0)
    profit_per_order: Mapped[float] = mapped_column(Float, default=0.0)
    avg_attribution_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    content_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    score_breakdown: Mapped[str] = mapped_column(Text, default="{}")
    finance_quality: Mapped[str] = mapped_column(String(30), default="estimated", index=True)
    # actual | mixed | estimated

    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_content_profit_scope", "scope_type", "scope_key", "calculated_at"),
        Index("ix_content_profit_campaign_product", "campaign_key", "product_id"),
    )


class ContentStrategyProfile(Base):
    """수익성 피드백으로 갱신되는 콘텐츠 전략 프로필."""
    __tablename__ = "content_strategy_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(200), default="", index=True)

    preferred_angles_json: Mapped[str] = mapped_column(Text, default="[]")
    avoid_angles_json: Mapped[str] = mapped_column(Text, default="[]")
    winning_patterns_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")

    sample_posts: Mapped[int] = mapped_column(Integer, default=0)
    sample_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    avg_content_score: Mapped[float] = mapped_column(Float, default=0.0)
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
