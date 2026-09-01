"""Seller OS REST boundary for product detail-page -> Threads campaigns."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.orchestration.product_growth import (
    apply_detail_assets,
    attach_image_generation,
    create_workflow,
    ensure_workflow_tracking,
    get_workflow,
    list_workflows,
    prepare_threads_drafts,
    queue_detail_generation,
    register_detail_assets,
    schedule_workflow_post,
    stage_attached_social_visual,
    tracking_public_url,
    use_product_social_visual,
    workflow_to_dict,
)
from app.social.threads.media import media_base_is_public
from app.social.threads.zalpa_content import ANGLES, TONE_LABELS


router = APIRouter(prefix="/product-growth", tags=["product-growth"])


class WorkflowCreateRequest(BaseModel):
    product_id: int
    campaign_key: str = ""
    target_platform: Literal["smartstore", "coupang"] = "smartstore"
    destination_url: str = ""
    cta_keyword: str = ""
    threads_angle: str = "problem_solution"
    threads_tone: str = "zalpa"


class DraftPrepareRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=5)
    force: bool = False
    create_tracking: bool = True


class DetailAssetsRequest(BaseModel):
    image_urls: list[str] = Field(default_factory=list, max_length=20)
    apply: bool = True


class DetailGenerateRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=5)
    reference_url: str = ""
    apply: bool = True


class ImageGenerationAttachRequest(BaseModel):
    generation_id: int


class VisualStageRequest(BaseModel):
    image_index: int = Field(default=0, ge=0, le=20)


class ScheduleWorkflowRequest(BaseModel):
    draft_id: int
    scheduled_at: datetime
    media_source: Literal["workflow", "product", "none"] = "workflow"
    include_tracking_url: bool = True


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _public_response(row) -> dict:
    data = workflow_to_dict(row)
    generated = data.get("detail", {}).get("generated", [])
    if isinstance(generated, list):
        data["detail"]["generated"] = [
            {k: item.get(k) for k in ("role", "public_url") if item.get(k)}
            for item in generated
            if isinstance(item, dict)
        ]
    return jsonable_encoder(data)


@router.get("/catalog")
def catalog() -> dict:
    return {
        "target_platforms": ["smartstore", "coupang"],
        "threads_angles": ANGLES,
        "threads_tones": TONE_LABELS,
        "social_visual_sources": ["workflow", "product", "none"],
        "threads_media_public": media_base_is_public(),
        "design_rules": {
            "detail_page": "reference-grounded product imagery",
            "stable_diffusion": "social/lifestyle visual only; not authoritative product identity",
            "publishing": "schedule first; existing Threads scheduler owns external publish",
            "tracking": "campaign_key and product_id are preserved through click/order attribution",
        },
    }


@router.post("/workflows", status_code=status.HTTP_201_CREATED)
def workflow_create(body: WorkflowCreateRequest) -> dict:
    try:
        row = create_workflow(**body.model_dump())
        return _public_response(row)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workflows")
def workflows(
    limit: int = Query(default=100, ge=1, le=300),
    product_id: int | None = None,
) -> dict:
    rows = list_workflows(limit=limit, product_id=product_id)
    return {"count": len(rows), "items": [_public_response(row) for row in rows]}


@router.get("/workflows/{workflow_id}")
def workflow_get(workflow_id: int) -> dict:
    row = get_workflow(workflow_id)
    if not row:
        raise HTTPException(status_code=404, detail="workflow not found")
    return _public_response(row)


@router.post("/workflows/{workflow_id}/tracking")
def workflow_tracking(workflow_id: int) -> dict:
    try:
        link = ensure_workflow_tracking(workflow_id)
        return {"id": link.id, "code": link.code, "url": tracking_public_url(link), "campaign_key": link.campaign_key}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/threads-drafts", status_code=status.HTTP_201_CREATED)
def workflow_threads_drafts(workflow_id: int, body: DraftPrepareRequest) -> dict:
    try:
        if body.create_tracking:
            row = get_workflow(workflow_id)
            if not row:
                raise LookupError("workflow not found")
            if row.destination_url:
                ensure_workflow_tracking(workflow_id)
        drafts = prepare_threads_drafts(workflow_id, count=body.count, force=body.force)
        return {
            "count": len(drafts),
            "drafts": [
                {"id": d.id, "body": d.body, "score": d.score, "status": d.status, "target_url": d.target_url}
                for d in drafts
            ],
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/detail-assets")
def workflow_detail_assets(workflow_id: int, body: DetailAssetsRequest) -> dict:
    try:
        return register_detail_assets(workflow_id, body.image_urls, apply=body.apply)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/detail-assets/apply")
def workflow_detail_apply(workflow_id: int) -> dict:
    try:
        return apply_detail_assets(workflow_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/detail-generation", status_code=status.HTTP_202_ACCEPTED)
def workflow_detail_generate(workflow_id: int, body: DetailGenerateRequest) -> dict:
    """Queue the explicitly requested paid detail-image generation job."""
    try:
        return queue_detail_generation(
            workflow_id,
            count=body.count,
            reference_url=body.reference_url,
            apply=body.apply,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/social-visual/attach")
def workflow_visual_attach(workflow_id: int, body: ImageGenerationAttachRequest) -> dict:
    try:
        return attach_image_generation(workflow_id, body.generation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/social-visual/stage")
def workflow_visual_stage(workflow_id: int, body: VisualStageRequest) -> dict:
    try:
        return stage_attached_social_visual(workflow_id, body.image_index)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, IndexError, FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/social-visual/product")
def workflow_visual_product(workflow_id: int, body: VisualStageRequest) -> dict:
    try:
        return use_product_social_visual(workflow_id, body.image_index)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IndexError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/schedules", status_code=status.HTTP_201_CREATED)
def workflow_schedule(workflow_id: int, body: ScheduleWorkflowRequest) -> dict:
    try:
        row = schedule_workflow_post(
            workflow_id,
            draft_id=body.draft_id,
            scheduled_at=_to_utc_naive(body.scheduled_at),
            media_source=body.media_source,
            include_tracking_url=body.include_tracking_url,
        )
        return jsonable_encoder({
            "id": row.id,
            "status": row.status,
            "campaign_key": row.campaign_key,
            "media_type": row.media_type,
            "media_url": row.media_url,
            "scheduled_at_utc": row.scheduled_at,
        })
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


__all__ = ["router"]
