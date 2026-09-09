"""Persistent audit/apply history for the marketplace SEO optimizer.

Legacy AutoSellerAI tables are created with ``Base.metadata.create_all`` rather than
Alembic's canonical ``os_*`` migration stream.  This module deliberately keeps the
new SEO audit tables in that legacy namespace and exposes an explicit schema helper
so the Streamlit page can be used immediately after deployment.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, _get_engine


class MarketSeoAudit(Base):
    __tablename__ = "market_seo_audits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(80), index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    listing_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    platform_product_id: Mapped[str] = mapped_column(String(200), default="")

    product_name: Mapped[str] = mapped_column(String(300), default="")
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    proposed_score: Mapped[float] = mapped_column(Float, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    priority_grade: Mapped[str] = mapped_column(String(10), default="C", index=True)
    classification: Mapped[str] = mapped_column(String(50), default="", index=True)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_orders: Mapped[int] = mapped_column(Integer, default=0)
    sales_protected: Mapped[bool] = mapped_column(default=False)

    current_json: Mapped[str] = mapped_column(Text, default="{}")
    proposed_json: Mapped[str] = mapped_column(Text, default="{}")
    issues_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    data_sources_json: Mapped[str] = mapped_column(Text, default="{}")
    limitations_json: Mapped[str] = mapped_column(Text, default="[]")
    selected_fields_json: Mapped[str] = mapped_column(Text, default="[]")

    status: Mapped[str] = mapped_column(String(30), default="AUDITED", index=True)
    # AUDITED | APPROVED | APPLIED | PARTIAL | APPLY_FAILED | REJECTED
    error: Mapped[str] = mapped_column(Text, default="")
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_market_seo_listing_analyzed", "listing_id", "analyzed_at"),
        Index("ix_market_seo_product_platform", "product_id", "platform"),
    )


class MarketSeoApplyLog(Base):
    __tablename__ = "market_seo_apply_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    audit_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    listing_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    platform_product_id: Mapped[str] = mapped_column(String(200), default="")
    selected_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="RUNNING", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)



def ensure_market_seo_schema() -> None:
    """Create only the optimizer's legacy tables when they do not yet exist."""
    engine = _get_engine()
    MarketSeoAudit.__table__.create(engine, checkfirst=True)
    MarketSeoApplyLog.__table__.create(engine, checkfirst=True)


__all__ = ["MarketSeoAudit", "MarketSeoApplyLog", "ensure_market_seo_schema"]
