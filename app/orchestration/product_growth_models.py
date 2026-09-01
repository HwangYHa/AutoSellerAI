"""Persistent state for product detail-page -> Threads growth campaigns."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, _get_engine
from app.sqlite_runtime import retry_sqlite_write


class ProductGrowthWorkflow(Base):
    __tablename__ = "product_growth_workflows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    campaign_key: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)

    target_platform: Mapped[str] = mapped_column(String(30), default="smartstore", index=True)
    destination_url: Mapped[str] = mapped_column(Text, default="")
    cta_keyword: Mapped[str] = mapped_column(String(100), default="")
    threads_angle: Mapped[str] = mapped_column(String(40), default="problem_solution")
    threads_tone: Mapped[str] = mapped_column(String(30), default="zalpa")

    detail_image_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    detail_generated_json: Mapped[str] = mapped_column(Text, default="[]")
    image_generation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    social_media_url: Mapped[str] = mapped_column(Text, default="")

    tracking_link_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    draft_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    scheduled_post_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    steps_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("product_id", "campaign_key", name="uq_product_growth_product_campaign"),
    )


def ensure_product_growth_schema() -> None:
    engine = _get_engine()

    def create() -> None:
        Base.metadata.create_all(bind=engine, tables=[ProductGrowthWorkflow.__table__])

    retry_sqlite_write(create, attempts=6)


__all__ = ["ProductGrowthWorkflow", "ensure_product_growth_schema"]
