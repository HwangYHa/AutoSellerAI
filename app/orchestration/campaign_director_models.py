"""Persistent AI Campaign Director plans for product-growth workflows."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, _get_engine
from app.sqlite_runtime import retry_sqlite_write


class CampaignDirectorPlan(Base):
    __tablename__ = "campaign_director_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(Integer, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    source: Mapped[str] = mapped_column(String(30), default="rules+performance", index=True)
    status: Mapped[str] = mapped_column(String(30), default="planned", index=True)
    plan_json: Mapped[str] = mapped_column(Text, default="{}")
    execution_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("workflow_id", name="uq_campaign_director_workflow"),
    )


def ensure_campaign_director_schema() -> None:
    engine = _get_engine()

    def create() -> None:
        Base.metadata.create_all(bind=engine, tables=[CampaignDirectorPlan.__table__])

    retry_sqlite_write(create, attempts=6)


__all__ = ["CampaignDirectorPlan", "ensure_campaign_director_schema"]
