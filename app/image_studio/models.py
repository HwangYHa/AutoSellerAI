from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, _get_engine
from app.sqlite_runtime import retry_sqlite_write


class AIImageGeneration(Base):
    __tablename__ = "ai_image_generations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rq_job_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    provider: Mapped[str] = mapped_column(String(40), default="stable-diffusion-webui")
    preset: Mapped[str] = mapped_column(String(80), default="")
    subject_summary: Mapped[str] = mapped_column(String(300), default="")

    request_json: Mapped[str] = mapped_column(Text, default="{}")
    prompt: Mapped[str] = mapped_column(Text, default="")
    negative_prompt: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    response_info_json: Mapped[str] = mapped_column(Text, default="{}")
    image_paths_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    error: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def ensure_image_studio_schema() -> None:
    engine = _get_engine()

    def create() -> None:
        Base.metadata.create_all(bind=engine, tables=[AIImageGeneration.__table__])

    retry_sqlite_write(create, attempts=6)


__all__ = ["AIImageGeneration", "ensure_image_studio_schema"]
