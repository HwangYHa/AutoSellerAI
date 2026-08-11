from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SocialContentDraft(Base):
    __tablename__ = "social_content_drafts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    channel: Mapped[str] = mapped_column(String(30), default="threads", index=True)
    angle: Mapped[str] = mapped_column(String(40), default="problem_solution", index=True)
    body: Mapped[str] = mapped_column(Text)
    cta_keyword: Mapped[str] = mapped_column(String(100), default="")
    target_platform: Mapped[str] = mapped_column(String(30), default="smartstore", index=True)
    target_url: Mapped[str] = mapped_column(Text, default="")
    tracking_link_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ai_source: Mapped[str] = mapped_column(String(30), default="rule")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    # draft | approved | scheduled | published | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScheduledSocialPost(Base):
    __tablename__ = "scheduled_social_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    channel: Mapped[str] = mapped_column(String(30), default="threads", index=True)
    content: Mapped[str] = mapped_column(Text)
    campaign_key: Mapped[str] = mapped_column(String(120), default="", index=True)
    cta_keyword: Mapped[str] = mapped_column(String(100), default="")
    tracking_link_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(30), default="scheduled", index=True)
    # scheduled | publishing | published | failed | cancelled
    threads_post_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_social_schedule_due", "status", "scheduled_at"),
    )


class TrackingLink(Base):
    __tablename__ = "tracking_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    channel: Mapped[str] = mapped_column(String(30), default="threads", index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)  # smartstore | coupang
    destination_url: Mapped[str] = mapped_column(Text)
    campaign_key: Mapped[str] = mapped_column(String(120), default="", index=True)
    post_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TrackingClick(Base):
    __tablename__ = "tracking_clicks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tracking_link_id: Mapped[int] = mapped_column(Integer, index=True)
    click_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    referer: Mapped[str] = mapped_column(Text, default="")
    clicked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_tracking_click_link_time", "tracking_link_id", "clicked_at"),
    )


class OrderAttribution(Base):
    __tablename__ = "order_attributions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform_order_row_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    platform_order_id: Mapped[str] = mapped_column(String(200), index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    tracking_link_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    click_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    campaign_key: Mapped[str] = mapped_column(String(120), default="", index=True)
    channel: Mapped[str] = mapped_column(String(30), default="threads", index=True)
    attribution_type: Mapped[str] = mapped_column(String(30), default="unattributed", index=True)
    # deterministic | probabilistic | unattributed
    confidence: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    order_amount: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(500), default="")
    attributed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
