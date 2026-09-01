"""Product-centric detail-page -> Threads campaign orchestration.

The workflow deliberately separates reversible preparation from paid/external actions:
- product/detail state and Threads drafts/tracking are prepared locally;
- paid detail-image generation is explicitly queued on the existing image worker;
- Threads publishing remains delegated to ScheduledSocialPost + the existing scheduler;
- Stable Diffusion output is only a social/lifestyle visual, never a source of truth for
  exact product identity.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from redis import Redis
from rq import Queue
from sqlalchemy import desc, select

from app.db import Product, get_db
from app.image_studio.service import get_generation, generation_to_dict, resolve_generation_image
from app.media.ai_detail_page import build_detail_html
from app.orchestration.product_growth_models import ProductGrowthWorkflow, ensure_product_growth_schema
from app.social.threads.content_engine import suggest_comment_keyword
from app.social.threads.growth_models import OrderAttribution, ScheduledSocialPost, SocialContentDraft, TrackingLink
from app.social.threads.media import media_base_is_public, save_threads_image, threads_media_public_url
from app.social.threads.migrations import ensure_threads_schema
from app.social.threads.models import ThreadsPost
from app.social.threads.tracking import create_tracking_link
from app.social.threads.zalpa_content import ANGLES, TONE_LABELS, generate_threads_content
from app.sqlite_runtime import retry_sqlite_write


_ALLOWED_PLATFORMS = {"smartstore", "coupang"}
_ACTIVE_SCHEDULE_STATES = {"scheduled", "publishing", "published"}


def _loads(value: str, fallback):
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _redis() -> Redis:
    return Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _campaign_key(product_id: int) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"pg-{int(product_id)}-{stamp}-{secrets.token_hex(3)}"


def _clean_campaign_key(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣_.:-]+", "-", str(value or "").strip()).strip("-")
    return cleaned[:120]


def _product_dict(product: Product) -> dict[str, Any]:
    return {
        "id": product.id,
        "sku": product.sku,
        "source": product.source,
        "source_id": product.source_id,
        "source_url": product.source_url,
        "name": product.name,
        "category": product.category,
        "brand": product.brand,
        "origin": product.origin,
        "material": product.material,
        "sell_price": float(product.sell_price or 0),
        "supply_price": float(product.supply_price or 0),
        "images": _loads(product.images, []),
        "detail_images": _loads(product.detail_images, []),
        "options": _loads(product.options, []),
        "detail_html": product.detail_html or "",
        "status": product.status,
    }


def _set_workflow(workflow_id: int, **values) -> None:
    def write() -> None:
        with get_db() as db:
            row = db.get(ProductGrowthWorkflow, int(workflow_id))
            if not row:
                return
            for key, value in values.items():
                setattr(row, key, value)
            db.commit()

    retry_sqlite_write(write, attempts=6)


def _merge_step(workflow_id: int, key: str, payload: dict[str, Any]) -> None:
    def write() -> None:
        with get_db() as db:
            row = db.get(ProductGrowthWorkflow, int(workflow_id))
            if not row:
                return
            steps = _loads(row.steps_json, {})
            steps[key] = {**payload, "updated_at": datetime.utcnow().isoformat()}
            row.steps_json = json.dumps(steps, ensure_ascii=False, default=str)
            db.commit()

    retry_sqlite_write(write, attempts=6)


def create_workflow(
    product_id: int,
    *,
    campaign_key: str = "",
    target_platform: str = "smartstore",
    destination_url: str = "",
    cta_keyword: str = "",
    threads_angle: str = "problem_solution",
    threads_tone: str = "zalpa",
) -> ProductGrowthWorkflow:
    ensure_threads_schema()
    ensure_product_growth_schema()
    platform = str(target_platform or "").strip().lower()
    if platform not in _ALLOWED_PLATFORMS:
        raise ValueError("target_platform must be smartstore or coupang")
    if destination_url and not str(destination_url).startswith(("http://", "https://")):
        raise ValueError("destination_url must be an absolute http(s) URL")
    if threads_angle not in ANGLES:
        raise ValueError(f"unsupported Threads angle: {threads_angle}")
    if threads_tone not in TONE_LABELS:
        raise ValueError(f"unsupported Threads tone: {threads_tone}")

    with get_db() as db:
        product = db.get(Product, int(product_id))
        if not product:
            raise LookupError("product not found")
        product_ctx = _product_dict(product)

    key = _clean_campaign_key(campaign_key) or _campaign_key(product_id)
    if campaign_key and not key:
        raise ValueError("campaign_key is invalid")
    cta = str(cta_keyword or "").strip()[:100] or suggest_comment_keyword(product_ctx)

    with get_db() as db:
        existing = db.scalar(
            select(ProductGrowthWorkflow).where(
                ProductGrowthWorkflow.product_id == int(product_id),
                ProductGrowthWorkflow.campaign_key == key,
            )
        )
        if existing:
            db.expunge(existing)
            return existing
        row = ProductGrowthWorkflow(
            product_id=int(product_id),
            campaign_key=key,
            target_platform=platform,
            destination_url=str(destination_url or "").strip(),
            cta_keyword=cta,
            threads_angle=threads_angle,
            threads_tone=threads_tone,
            steps_json=json.dumps({"created": {"ok": True, "at": datetime.utcnow().isoformat()}}, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        db.expunge(row)
        return row


def get_workflow(workflow_id: int) -> ProductGrowthWorkflow | None:
    ensure_product_growth_schema()
    with get_db() as db:
        row = db.get(ProductGrowthWorkflow, int(workflow_id))
        if row:
            db.expunge(row)
        return row


def list_workflows(limit: int = 100, product_id: int | None = None) -> list[ProductGrowthWorkflow]:
    ensure_product_growth_schema()
    safe_limit = max(1, min(int(limit), 300))
    with get_db() as db:
        stmt = select(ProductGrowthWorkflow)
        if product_id is not None:
            stmt = stmt.where(ProductGrowthWorkflow.product_id == int(product_id))
        rows = list(db.scalars(stmt.order_by(desc(ProductGrowthWorkflow.created_at)).limit(safe_limit)).all())
        for row in rows:
            db.expunge(row)
        return rows


def ensure_workflow_tracking(workflow_id: int) -> TrackingLink:
    row = get_workflow(workflow_id)
    if not row:
        raise LookupError("workflow not found")
    if row.tracking_link_id:
        with get_db() as db:
            link = db.get(TrackingLink, int(row.tracking_link_id))
            if link:
                db.expunge(link)
                return link
    if not row.destination_url:
        raise ValueError("destination_url is required before creating a tracking link")
    link = create_tracking_link(
        row.product_id,
        row.target_platform,
        row.destination_url,
        row.campaign_key,
        "threads",
    )
    _set_workflow(workflow_id, tracking_link_id=link.id, error="")
    _merge_step(workflow_id, "tracking", {"ok": True, "tracking_link_id": link.id, "code": link.code})
    return link


def tracking_public_url(link: TrackingLink) -> str:
    base = str(os.getenv("PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    return f"{base}/t/{link.code}" if base else f"/t/{link.code}"


def prepare_threads_drafts(workflow_id: int, *, count: int = 3, force: bool = False) -> list[SocialContentDraft]:
    row = get_workflow(workflow_id)
    if not row:
        raise LookupError("workflow not found")
    if not force:
        ids = [int(x) for x in _loads(row.draft_ids_json, []) if str(x).isdigit()]
        if ids:
            with get_db() as db:
                existing = [db.get(SocialContentDraft, x) for x in ids]
                existing = [x for x in existing if x is not None]
                for item in existing:
                    db.expunge(item)
                if existing:
                    return existing

    link = ensure_workflow_tracking(workflow_id) if row.destination_url else None
    with get_db() as db:
        product = db.get(Product, row.product_id)
        if not product:
            raise LookupError("product not found")
        context = _product_dict(product)

    variants = generate_threads_content(
        context,
        row.threads_angle,
        row.cta_keyword,
        max(1, min(int(count), 5)),
        tone=row.threads_tone,
    )
    target_url = tracking_public_url(link) if link else row.destination_url
    created_ids: list[int] = []
    with get_db() as db:
        for variant in variants:
            draft = SocialContentDraft(
                product_id=row.product_id,
                channel="threads",
                angle=row.threads_angle,
                body=str(variant.get("body") or "")[:500],
                cta_keyword=str(variant.get("cta_keyword") or row.cta_keyword)[:100],
                target_platform=row.target_platform,
                target_url=target_url,
                tracking_link_id=link.id if link else None,
                ai_source=str(variant.get("source") or "rule")[:30],
                score=float(variant.get("score") or 0),
                status="draft",
            )
            db.add(draft)
            db.flush()
            created_ids.append(draft.id)
        db.commit()

    _set_workflow(workflow_id, draft_ids_json=json.dumps(created_ids), error="")
    _merge_step(workflow_id, "threads_drafts", {"ok": True, "draft_ids": created_ids, "count": len(created_ids)})
    return _drafts_by_ids(created_ids)


def _drafts_by_ids(ids: list[int]) -> list[SocialContentDraft]:
    if not ids:
        return []
    with get_db() as db:
        rows = list(db.scalars(select(SocialContentDraft).where(SocialContentDraft.id.in_(ids))).all())
        by_id = {row.id: row for row in rows}
        ordered = [by_id[x] for x in ids if x in by_id]
        for row in ordered:
            db.expunge(row)
        return ordered


def attach_image_generation(workflow_id: int, generation_id: int) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise LookupError("workflow not found")
    generation = get_generation(int(generation_id))
    if not generation:
        raise LookupError("image generation not found")
    data = generation_to_dict(generation)
    if data.get("status") != "completed" or not data.get("image_paths"):
        raise ValueError("only completed Stable Diffusion generations with images can be attached")
    _set_workflow(workflow_id, image_generation_id=int(generation_id), social_media_url="", error="")
    _merge_step(workflow_id, "social_visual", {"ok": True, "generation_id": int(generation_id), "staged": False})
    return {"generation_id": int(generation_id), "image_count": len(data.get("image_paths") or [])}


def stage_attached_social_visual(workflow_id: int, image_index: int = 0) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise LookupError("workflow not found")
    if not workflow.image_generation_id:
        raise ValueError("attach a completed Stable Diffusion generation first")
    source = resolve_generation_image(workflow.image_generation_id, int(image_index))
    payload = Path(source).read_bytes()
    filename = save_threads_image(source.name, payload, "image/png")
    public_url = threads_media_public_url(filename)
    is_public = media_base_is_public()
    _set_workflow(workflow_id, social_media_url=public_url, error="")
    _merge_step(
        workflow_id,
        "social_visual",
        {"ok": True, "generation_id": workflow.image_generation_id, "staged": True, "url": public_url, "public": is_public},
    )
    return {"filename": filename, "media_url": public_url, "public": is_public}


def use_product_social_visual(workflow_id: int, image_index: int = 0) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise LookupError("workflow not found")
    with get_db() as db:
        product = db.get(Product, workflow.product_id)
        if not product:
            raise LookupError("product not found")
        images = [str(x) for x in _loads(product.images, []) if str(x).startswith(("http://", "https://"))]
    if image_index < 0 or image_index >= len(images):
        raise IndexError("product image index out of range")
    url = images[image_index]
    _set_workflow(workflow_id, social_media_url=url, error="")
    _merge_step(workflow_id, "social_visual", {"ok": True, "source": "product", "url": url, "public": True})
    return {"media_url": url, "public": True, "source": "product"}


def register_detail_assets(workflow_id: int, image_urls: list[str], *, apply: bool = True) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise LookupError("workflow not found")
    urls = list(dict.fromkeys(str(x).strip() for x in image_urls if str(x).strip().startswith(("http://", "https://"))))
    _set_workflow(workflow_id, detail_image_urls_json=json.dumps(urls, ensure_ascii=False), error="")
    if not apply:
        _merge_step(workflow_id, "detail_page", {"ok": True, "registered": len(urls), "applied": False})
        return {"registered": len(urls), "applied": False, "image_urls": urls}
    result = apply_detail_assets(workflow_id)
    return {**result, "registered": len(urls)}


def apply_detail_assets(workflow_id: int) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise LookupError("workflow not found")
    workflow_urls = [str(x) for x in _loads(workflow.detail_image_urls_json, []) if str(x).startswith(("http://", "https://"))]
    with get_db() as db:
        product = db.get(Product, workflow.product_id)
        if not product:
            raise LookupError("product not found")
        existing = [str(x) for x in _loads(product.detail_images, []) if str(x).startswith(("http://", "https://"))]
        merged = list(dict.fromkeys([*existing, *workflow_urls]))
        context = _product_dict(product)
        html = build_detail_html(context, merged)
        product.detail_images = json.dumps(merged, ensure_ascii=False)
        if html:
            product.detail_html = html
        db.commit()
    _merge_step(workflow_id, "detail_page", {"ok": True, "applied": True, "image_count": len(merged), "html": bool(html)})
    return {"applied": True, "image_count": len(merged), "detail_html_ready": bool(html)}


def queue_detail_generation(
    workflow_id: int,
    *,
    count: int = 3,
    reference_url: str = "",
    apply: bool = True,
) -> dict[str, Any]:
    """Explicitly queue the paid reference-based detail image job; never run it in HTTP."""
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise LookupError("workflow not found")
    from app.orchestration.product_growth_tasks import run_detail_generation_job

    connection = _redis()
    connection.ping()
    queue = Queue("image", connection=connection, default_timeout=int(os.getenv("IMAGE_AI_JOB_TIMEOUT_SECONDS", "900")))
    job = queue.enqueue(
        run_detail_generation_job,
        int(workflow_id),
        max(1, min(int(count), 5)),
        str(reference_url or ""),
        bool(apply),
        job_timeout=int(os.getenv("IMAGE_AI_JOB_TIMEOUT_SECONDS", "900")),
        result_ttl=86400,
        failure_ttl=604800,
    )
    _merge_step(workflow_id, "detail_generation", {"ok": True, "status": "queued", "job_id": job.id, "count": count})
    return {"accepted": True, "job_id": job.id, "queue": "image"}


def schedule_workflow_post(
    workflow_id: int,
    *,
    draft_id: int,
    scheduled_at: datetime,
    media_source: str = "workflow",
    include_tracking_url: bool = True,
) -> ScheduledSocialPost:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise LookupError("workflow not found")
    if scheduled_at <= datetime.utcnow():
        raise ValueError("scheduled_at must be in the future")
    link = ensure_workflow_tracking(workflow_id) if workflow.destination_url else None

    with get_db() as db:
        draft = db.get(SocialContentDraft, int(draft_id))
        if not draft or draft.product_id != workflow.product_id:
            raise LookupError("draft not found for workflow product")
        allowed_ids = {int(x) for x in _loads(workflow.draft_ids_json, []) if str(x).isdigit()}
        if allowed_ids and draft.id not in allowed_ids:
            raise ValueError("draft does not belong to this workflow campaign")
        content = str(draft.body or "").strip()

    tracking_url = tracking_public_url(link) if link else ""
    if include_tracking_url and tracking_url:
        suffix = f"\n\n{tracking_url}"
        content = content[: max(0, 500 - len(suffix))].rstrip() + suffix

    source = str(media_source or "workflow").strip().lower()
    media_type = "TEXT"
    media_url = ""
    if source == "workflow":
        media_url = str(workflow.social_media_url or "").strip()
        if media_url:
            if media_url.startswith(("http://localhost", "http://127.", "http://0.0.0.0")):
                raise ValueError("Threads image media URL must be publicly reachable")
            media_type = "IMAGE"
    elif source == "product":
        visual = use_product_social_visual(workflow_id, 0)
        media_url = visual["media_url"]
        media_type = "IMAGE"
    elif source in {"none", "text"}:
        pass
    else:
        raise ValueError("media_source must be workflow, product or none")

    with get_db() as db:
        scheduled = ScheduledSocialPost(
            draft_id=int(draft_id),
            product_id=workflow.product_id,
            channel="threads",
            content=content[:500],
            scheduled_at=scheduled_at,
            campaign_key=workflow.campaign_key,
            cta_keyword=workflow.cta_keyword,
            tracking_link_id=link.id if link else None,
            media_type=media_type,
            media_url=media_url,
            alt_text=f"{workflow.campaign_key} 상품 콘텐츠"[:1000],
            carousel_items_json="[]",
            status="scheduled",
        )
        db.add(scheduled)
        draft = db.get(SocialContentDraft, int(draft_id))
        if draft:
            draft.status = "scheduled"
            draft.tracking_link_id = link.id if link else None
        db.commit()
        db.refresh(scheduled)
        schedule_id = scheduled.id
        db.expunge(scheduled)

    ids = [int(x) for x in _loads(workflow.scheduled_post_ids_json, []) if str(x).isdigit()]
    if schedule_id not in ids:
        ids.append(schedule_id)
    _set_workflow(workflow_id, scheduled_post_ids_json=json.dumps(ids), error="")
    _merge_step(workflow_id, "schedule", {"ok": True, "schedule_id": schedule_id, "media_type": media_type})
    return scheduled


def workflow_to_dict(row: ProductGrowthWorkflow) -> dict[str, Any]:
    with get_db() as db:
        product = db.get(Product, row.product_id)
        product_data = _product_dict(product) if product else None
        drafts = list(db.scalars(select(SocialContentDraft).where(SocialContentDraft.id.in_(_loads(row.draft_ids_json, []) or [-1]))).all())
        schedules = list(db.scalars(select(ScheduledSocialPost).where(ScheduledSocialPost.campaign_key == row.campaign_key)).all())
        posts = list(db.scalars(select(ThreadsPost).where(ThreadsPost.campaign_key == row.campaign_key)).all())
        attributions = list(db.scalars(select(OrderAttribution).where(OrderAttribution.campaign_key == row.campaign_key)).all())
        tracking = db.get(TrackingLink, row.tracking_link_id) if row.tracking_link_id else None

    detail_ready = bool(product_data and (product_data.get("detail_html") or product_data.get("detail_images")))
    draft_ready = bool(drafts)
    scheduled = any(x.status in _ACTIVE_SCHEDULE_STATES for x in schedules)
    published = bool(posts) or any(x.status == "published" for x in schedules)
    tracking_ready = bool(tracking)
    if row.error:
        status = "partial_failed"
    elif published:
        status = "published"
    elif scheduled:
        status = "scheduled"
    elif draft_ready and tracking_ready:
        status = "ready_to_schedule"
    elif draft_ready:
        status = "content_ready"
    else:
        status = "draft"

    return {
        "id": row.id,
        "product_id": row.product_id,
        "campaign_key": row.campaign_key,
        "status": status,
        "stored_status": row.status,
        "target_platform": row.target_platform,
        "destination_url": row.destination_url,
        "cta_keyword": row.cta_keyword,
        "threads_angle": row.threads_angle,
        "threads_tone": row.threads_tone,
        "product": product_data,
        "detail": {
            "ready": detail_ready,
            "workflow_image_urls": _loads(row.detail_image_urls_json, []),
            "generated": _loads(row.detail_generated_json, []),
        },
        "social_visual": {
            "image_generation_id": row.image_generation_id,
            "media_url": row.social_media_url,
            "public_media_base": media_base_is_public(),
        },
        "tracking": {
            "id": tracking.id if tracking else None,
            "code": tracking.code if tracking else "",
            "url": tracking_public_url(tracking) if tracking else "",
            "ready": tracking_ready,
        },
        "drafts": [
            {"id": x.id, "body": x.body, "angle": x.angle, "score": x.score, "status": x.status, "target_url": x.target_url}
            for x in drafts
        ],
        "schedules": [
            {"id": x.id, "draft_id": x.draft_id, "status": x.status, "media_type": x.media_type, "media_url": x.media_url,
             "scheduled_at": x.scheduled_at, "threads_post_id": x.threads_post_id, "error": x.error}
            for x in schedules
        ],
        "performance": {
            "published_posts": len(posts),
            "attributed_orders": len(attributions),
            "attributed_revenue": sum(float(x.order_amount or 0) for x in attributions),
            "avg_confidence": (sum(float(x.confidence or 0) for x in attributions) / len(attributions)) if attributions else 0.0,
        },
        "steps": _loads(row.steps_json, {}),
        "error": row.error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "completed_at": row.completed_at,
    }


__all__ = [
    "create_workflow", "get_workflow", "list_workflows", "workflow_to_dict",
    "ensure_workflow_tracking", "prepare_threads_drafts", "attach_image_generation",
    "stage_attached_social_visual", "use_product_social_visual", "register_detail_assets",
    "apply_detail_assets", "queue_detail_generation", "schedule_workflow_post", "tracking_public_url",
]
