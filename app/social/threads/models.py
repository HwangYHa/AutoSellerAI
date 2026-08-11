from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ThreadsPost(Base):
    __tablename__ = "threads_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    threads_post_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    campaign_key: Mapped[str] = mapped_column(String(120), default="", index=True)
    content: Mapped[str] = mapped_column(Text)
    cta_keyword: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(30), default="published", index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ThreadsComment(Base):
    __tablename__ = "threads_comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    threads_comment_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    threads_post_id: Mapped[str] = mapped_column(String(200), index=True)
    author_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    author_username: Mapped[str] = mapped_column(String(200), default="")
    comment_text: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(40), default="UNKNOWN", index=True)
    purchase_intent_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    sentiment: Mapped[str] = mapped_column(String(20), default="neutral")
    requires_human: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_threads_comment_post_processed", "threads_post_id", "processed"),
    )


class ThreadsReply(Base):
    __tablename__ = "threads_replies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(Integer, index=True)
    threads_reply_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    reply_text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), default="rule")  # rule | ai | human
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ThreadsAutomationRule(Base):
    __tablename__ = "threads_automation_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    reply_template: Mapped[str] = mapped_column(Text)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
