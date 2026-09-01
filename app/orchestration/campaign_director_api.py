"""Seller OS REST API for AI Campaign Director."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.orchestration.campaign_director import (
    build_campaign_plan,
    get_campaign_plan,
    prepare_campaign,
    schedule_director_post,
)


router = APIRouter(prefix="/product-growth", tags=["campaign-director"])


class PlanRequest(BaseModel):
    force: bool = False


class PrepareRequest(BaseModel):
    allow_ai_content: bool = False
    allow_paid_detail_generation: bool = False
    draft_count: int = Field(default=3, ge=1, le=5)
    force_drafts: bool = False


class ScheduleRequest(BaseModel):
    scheduled_at: datetime
    draft_id: int | None = None
    media_source: Literal["auto", "workflow", "product", "detail", "none"] = "auto"
    include_tracking_url: bool = True


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/workflows/{workflow_id}/director")
def director_get(workflow_id: int) -> dict:
    row = get_campaign_plan(workflow_id)
    if not row:
        raise HTTPException(status_code=404, detail="campaign director plan not found")
    return jsonable_encoder(row)


@router.post("/workflows/{workflow_id}/director/plan", status_code=status.HTTP_201_CREATED)
def director_plan(workflow_id: int, body: PlanRequest) -> dict:
    try:
        return jsonable_encoder(build_campaign_plan(workflow_id, force=body.force))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/director/prepare")
def director_prepare(workflow_id: int, body: PrepareRequest) -> dict:
    try:
        return jsonable_encoder(
            prepare_campaign(
                workflow_id,
                allow_ai_content=body.allow_ai_content,
                allow_paid_detail_generation=body.allow_paid_detail_generation,
                draft_count=body.draft_count,
                force_drafts=body.force_drafts,
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/director/schedule", status_code=status.HTTP_201_CREATED)
def director_schedule(workflow_id: int, body: ScheduleRequest) -> dict:
    try:
        return jsonable_encoder(
            schedule_director_post(
                workflow_id,
                scheduled_at=_to_utc_naive(body.scheduled_at),
                draft_id=body.draft_id,
                media_source=body.media_source,
                include_tracking_url=body.include_tracking_url,
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


__all__ = ["router"]
