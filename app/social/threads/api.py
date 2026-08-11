from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from app.db import Product, get_db, init_db
from app.social.threads import growth_models as _growth_models  # register metadata
from app.social.threads import models as _models  # register metadata
from app.social.threads.client import ThreadsClient, ThreadsConfig, verify_webhook_signature
from app.social.threads.content_engine import generate_threads_content
from app.social.threads.growth_models import (
    OrderAttribution,
    ScheduledSocialPost,
    SocialContentDraft,
    TrackingLink,
)
from app.social.threads.models import ThreadsAutomationRule, ThreadsComment, ThreadsPost
from app.social.threads.tasks import enqueue_webhook_event
from app.social.threads.tracking import (
    attribute_recent_orders,
    attribution_summary,
    create_tracking_link,
    record_click,
)


class PublishRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    product_id: int | None = None
    campaign_key: str = ""
    cta_keyword: str = ""


class RuleRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    reply_template: str = Field(min_length=1, max_length=450)
    product_id: int | None = None
    priority: int = 100
    enabled: bool = True


class ContentGenerateRequest(BaseModel):
    product_id: int
    angle: str = "problem_solution"
    cta_keyword: str = ""
    count: int = Field(default=3, ge=1, le=5)
    target_platform: str = "smartstore"
    target_url: str = ""


class TrackingLinkRequest(BaseModel):
    product_id: int
    platform: str
    destination_url: str
    campaign_key: str = ""
    channel: str = "threads"


class ScheduleRequest(BaseModel):
    draft_id: int | None = None
    product_id: int
    content: str = Field(min_length=1, max_length=500)
    scheduled_at: datetime
    campaign_key: str = ""
    cta_keyword: str = ""
    tracking_link_id: int | None = None


app = FastAPI(title="AutoSellerAI Social Commerce API", version="0.2.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "threads-social-commerce"}


@app.get("/api/v1/threads/webhook")
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    cfg = ThreadsConfig.from_env()
    if hub_mode == "subscribe" and hub_verify_token == cfg.verify_token and hub_challenge:
        return int(hub_challenge) if hub_challenge.isdigit() else hub_challenge
    raise HTTPException(status_code=403, detail="webhook verification failed")


@app.post("/api/v1/threads/webhook", status_code=202)
async def receive_webhook(request: Request) -> dict[str, Any]:
    raw = await request.body()
    cfg = ThreadsConfig.from_env()
    if not verify_webhook_signature(raw, request.headers.get("x-hub-signature-256"), cfg.app_secret):
        raise HTTPException(status_code=401, detail="invalid webhook signature")
    payload = await request.json()
    auto_reply = os.getenv("THREADS_AUTO_REPLY", "false").lower() == "true"
    jobs: list[str] = []
    entries = payload.get("entry", []) if isinstance(payload, dict) else []
    if not entries:
        entries = [payload]
    for entry in entries:
        jobs.append(enqueue_webhook_event(entry, auto_reply=auto_reply))
    return {"accepted": len(jobs), "jobs": jobs}


@app.post("/api/v1/threads/posts", status_code=201)
def publish_post(body: PublishRequest) -> dict[str, Any]:
    remote_id = ThreadsClient().publish_text(body.text)
    with get_db() as db:
        post = ThreadsPost(
            threads_post_id=remote_id,
            product_id=body.product_id,
            campaign_key=body.campaign_key,
            content=body.text,
            cta_keyword=body.cta_keyword,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        return {"id": post.id, "threads_post_id": remote_id, "status": post.status}


@app.post("/api/v1/threads/content/generate", status_code=201)
def generate_content(body: ContentGenerateRequest) -> dict[str, Any]:
    with get_db() as db:
        product = db.get(Product, body.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="product not found")
        context = {
            "id": product.id,
            "name": product.name,
            "category": product.category,
            "brand": product.brand,
            "origin": product.origin,
            "material": product.material,
            "sell_price": product.sell_price,
        }
    variants = generate_threads_content(context, body.angle, body.cta_keyword, body.count)
    ids: list[int] = []
    with get_db() as db:
        for variant in variants:
            row = SocialContentDraft(
                product_id=body.product_id,
                angle=body.angle,
                body=variant["body"],
                cta_keyword=variant["cta_keyword"],
                target_platform=body.target_platform,
                target_url=body.target_url,
                ai_source=variant["source"],
                score=float(variant["score"]),
            )
            db.add(row)
            db.flush()
            ids.append(row.id)
        db.commit()
    return {"created": len(ids), "draft_ids": ids, "variants": variants}


@app.post("/api/v1/threads/tracking-links", status_code=201)
def make_tracking_link(body: TrackingLinkRequest, request: Request) -> dict[str, Any]:
    row = create_tracking_link(
        body.product_id, body.platform, body.destination_url, body.campaign_key, body.channel
    )
    public_base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not public_base:
        public_base = str(request.base_url).rstrip("/")
    return {"id": row.id, "code": row.code, "url": f"{public_base}/t/{row.code}"}


@app.get("/t/{code}")
def tracking_redirect(code: str, request: Request):
    xff = request.headers.get("x-forwarded-for", "")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "")
    try:
        link, click = record_click(
            code=code,
            ip=ip,
            user_agent=request.headers.get("user-agent", ""),
            referer=request.headers.get("referer", ""),
            hash_salt=os.getenv("TRACKING_HASH_SALT", "autoseller"),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="tracking link not found")
    response = RedirectResponse(link.destination_url, status_code=302)
    response.set_cookie(
        "as_click",
        click.click_id,
        max_age=60 * 60 * 24 * 7,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return response


@app.post("/api/v1/threads/schedules", status_code=201)
def schedule_post(body: ScheduleRequest) -> dict[str, Any]:
    scheduled_utc = _to_utc_naive(body.scheduled_at)
    if scheduled_utc <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="scheduled_at must be in the future")
    with get_db() as db:
        if not db.get(Product, body.product_id):
            raise HTTPException(status_code=404, detail="product not found")
        if body.draft_id and not db.get(SocialContentDraft, body.draft_id):
            raise HTTPException(status_code=404, detail="draft not found")
        if body.tracking_link_id and not db.get(TrackingLink, body.tracking_link_id):
            raise HTTPException(status_code=404, detail="tracking link not found")
        row = ScheduledSocialPost(
            draft_id=body.draft_id,
            product_id=body.product_id,
            content=body.content,
            scheduled_at=scheduled_utc,
            campaign_key=body.campaign_key,
            cta_keyword=body.cta_keyword,
            tracking_link_id=body.tracking_link_id,
        )
        db.add(row)
        if body.draft_id:
            draft = db.get(SocialContentDraft, body.draft_id)
            if draft:
                draft.status = "scheduled"
                draft.tracking_link_id = body.tracking_link_id
        db.commit()
        db.refresh(row)
        return {"id": row.id, "status": row.status, "scheduled_at_utc": row.scheduled_at.isoformat()}


@app.get("/api/v1/threads/schedules")
def list_schedules(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    with get_db() as db:
        rows = list(db.scalars(select(ScheduledSocialPost).order_by(desc(ScheduledSocialPost.scheduled_at)).limit(limit)).all())
    return [
        {
            "id": r.id,
            "product_id": r.product_id,
            "content": r.content,
            "campaign_key": r.campaign_key,
            "scheduled_at_utc": r.scheduled_at.isoformat(),
            "status": r.status,
            "threads_post_id": r.threads_post_id,
            "error": r.error,
        }
        for r in rows
    ]


@app.post("/api/v1/attribution/run")
def run_attribution(window_hours: int = Query(default=72, ge=1, le=720), force: bool = False) -> dict[str, Any]:
    return {**attribute_recent_orders(window_hours=window_hours, force=force), "summary": attribution_summary()}


@app.get("/api/v1/attribution")
def list_attribution(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    with get_db() as db:
        rows = list(db.scalars(select(OrderAttribution).order_by(desc(OrderAttribution.attributed_at)).limit(limit)).all())
    return {
        "summary": attribution_summary(),
        "items": [
            {
                "id": r.id,
                "platform": r.platform,
                "platform_order_id": r.platform_order_id,
                "product_id": r.product_id,
                "campaign_key": r.campaign_key,
                "type": r.attribution_type,
                "confidence": r.confidence,
                "order_amount": r.order_amount,
                "reason": r.reason,
                "attributed_at": r.attributed_at.isoformat(),
            }
            for r in rows
        ],
    }


@app.get("/api/v1/threads/comments")
def list_comments(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    with get_db() as db:
        rows = db.scalars(select(ThreadsComment).order_by(desc(ThreadsComment.received_at)).limit(limit)).all()
        return [
            {
                "id": row.id,
                "threads_comment_id": row.threads_comment_id,
                "threads_post_id": row.threads_post_id,
                "username": row.author_username,
                "text": row.comment_text,
                "intent": row.intent,
                "purchase_intent": row.purchase_intent_score,
                "requires_human": row.requires_human,
                "processed": row.processed,
                "received_at": row.received_at.isoformat(),
            }
            for row in rows
        ]


@app.get("/api/v1/threads/leads")
def hot_leads(min_score: float = Query(default=0.7, ge=0, le=1), limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    with get_db() as db:
        rows = db.scalars(
            select(ThreadsComment)
            .where(ThreadsComment.purchase_intent_score >= min_score)
            .order_by(desc(ThreadsComment.purchase_intent_score), desc(ThreadsComment.received_at))
            .limit(limit)
        ).all()
        return [
            {
                "id": row.id,
                "username": row.author_username,
                "text": row.comment_text,
                "intent": row.intent,
                "purchase_intent": row.purchase_intent_score,
                "requires_human": row.requires_human,
            }
            for row in rows
        ]


@app.post("/api/v1/threads/rules", status_code=201)
def create_rule(body: RuleRequest) -> dict[str, Any]:
    with get_db() as db:
        existing = db.scalar(select(ThreadsAutomationRule).where(ThreadsAutomationRule.keyword == body.keyword))
        if existing:
            raise HTTPException(status_code=409, detail="keyword already exists")
        rule = ThreadsAutomationRule(**body.model_dump())
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return {"id": rule.id, "keyword": rule.keyword, "enabled": rule.enabled}


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return value.astimezone(timezone.utc).replace(tzinfo=None)
