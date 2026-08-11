from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from app.db import Product, get_db, init_db
from app.social.threads import auth_models as _auth_models  # register metadata
from app.social.threads import growth_models as _growth_models  # register metadata
from app.social.threads import models as _models  # register metadata
from app.social.threads.auth import (
    DEFAULT_SCOPES,
    OAuthConfig,
    complete_oauth,
    credential_status,
    refresh_stored_credential,
)
from app.social.threads.client import ThreadsClient, ThreadsConfig, verify_webhook_signature
from app.social.threads.content_engine import generate_threads_content
from app.social.threads.growth_models import OrderAttribution, ScheduledSocialPost, SocialContentDraft, TrackingLink
from app.social.threads.models import ThreadsAutomationRule, ThreadsComment, ThreadsPost
from app.social.threads.tasks import enqueue_webhook_event
from app.social.threads.tracking import attribute_recent_orders, attribution_summary, create_tracking_link, record_click


class PublishRequest(BaseModel):
    text: str = Field(default="", max_length=500)
    product_id: int | None = None
    campaign_key: str = ""
    cta_keyword: str = ""
    media_type: str = "TEXT"
    media_url: str = ""
    alt_text: str = ""
    carousel_items: list[dict[str, str]] = Field(default_factory=list)


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
    content: str = Field(default="", max_length=500)
    scheduled_at: datetime
    campaign_key: str = ""
    cta_keyword: str = ""
    tracking_link_id: int | None = None
    media_type: str = "TEXT"
    media_url: str = ""
    alt_text: str = ""
    carousel_items: list[dict[str, str]] = Field(default_factory=list)


app = FastAPI(title="AutoSellerAI Social Commerce API", version="0.3.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "threads-social-commerce"}


# ── OAuth / 60-day token lifecycle ────────────────────────────────────
def _signed_oauth_state() -> str:
    cfg = OAuthConfig.from_env()
    cfg.validate()
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    raw = f"{ts}:{nonce}"
    sig = hmac.new(cfg.app_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{raw}:{sig}".encode()).decode().rstrip("=")


def _verify_oauth_state(state: str, max_age: int = 900) -> bool:
    try:
        padded = state + "=" * (-len(state) % 4)
        ts, nonce, supplied = base64.urlsafe_b64decode(padded.encode()).decode().split(":", 2)
        if abs(int(time.time()) - int(ts)) > max_age:
            return False
        cfg = OAuthConfig.from_env()
        raw = f"{ts}:{nonce}"
        expected = hmac.new(cfg.app_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, supplied)
    except Exception:
        return False


@app.get("/api/v1/threads/oauth/start")
def oauth_start() -> dict[str, Any]:
    cfg = OAuthConfig.from_env()
    cfg.validate()
    state = _signed_oauth_state()
    query = urlencode({
        "client_id": cfg.app_id,
        "redirect_uri": cfg.redirect_uri,
        "scope": ",".join(DEFAULT_SCOPES),
        "response_type": "code",
        "state": state,
    })
    return {"authorization_url": f"https://threads.net/oauth/authorize?{query}", "expires_in": 900}


@app.get("/api/v1/threads/oauth/callback")
def oauth_callback(code: str = Query(...), state: str = Query(...)):
    if not _verify_oauth_state(state):
        raise HTTPException(status_code=400, detail="invalid or expired OAuth state")
    try:
        complete_oauth(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Threads OAuth failed: {exc}")
    target = os.getenv("THREADS_OAUTH_SUCCESS_URL", "").strip() or os.getenv("SELLER_GUI_URL", "http://localhost:8501")
    return RedirectResponse(target, status_code=302)


@app.get("/api/v1/threads/oauth/status")
def oauth_status() -> dict[str, Any]:
    return credential_status()


@app.post("/api/v1/threads/oauth/refresh")
def oauth_refresh() -> dict[str, Any]:
    try:
        return refresh_stored_credential()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Threads webhook ───────────────────────────────────────────────────
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
    entries = payload.get("entry", []) if isinstance(payload, dict) else []
    if not entries:
        entries = [payload]
    jobs = [enqueue_webhook_event(entry, auto_reply=auto_reply) for entry in entries]
    return {"accepted": len(jobs), "jobs": jobs}


# ── Publish / content ─────────────────────────────────────────────────
def _publish_media(body: PublishRequest) -> str:
    media_type = body.media_type.upper().strip()
    client = ThreadsClient()
    if media_type == "TEXT":
        if not body.text.strip():
            raise HTTPException(status_code=400, detail="text is required for TEXT post")
        return client.publish_text(body.text.strip())
    if media_type == "IMAGE":
        return client.publish_image(body.media_url, body.text.strip(), body.alt_text)
    if media_type == "VIDEO":
        return client.publish_video(body.media_url, body.text.strip(), body.alt_text)
    if media_type == "CAROUSEL":
        return client.publish_carousel(body.carousel_items, body.text.strip())
    raise HTTPException(status_code=400, detail="media_type must be TEXT, IMAGE, VIDEO or CAROUSEL")


@app.post("/api/v1/threads/posts", status_code=201)
def publish_post(body: PublishRequest) -> dict[str, Any]:
    remote_id = _publish_media(body)
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
        return {"id": post.id, "threads_post_id": remote_id, "status": post.status, "media_type": body.media_type.upper()}


@app.post("/api/v1/threads/content/generate", status_code=201)
def generate_content(body: ContentGenerateRequest) -> dict[str, Any]:
    with get_db() as db:
        product = db.get(Product, body.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="product not found")
        context = {
            "id": product.id, "name": product.name, "category": product.category,
            "brand": product.brand, "origin": product.origin, "material": product.material,
            "sell_price": product.sell_price,
        }
    variants = generate_threads_content(context, body.angle, body.cta_keyword, body.count)
    ids: list[int] = []
    with get_db() as db:
        for variant in variants:
            row = SocialContentDraft(
                product_id=body.product_id, angle=body.angle, body=variant["body"],
                cta_keyword=variant["cta_keyword"], target_platform=body.target_platform,
                target_url=body.target_url, ai_source=variant["source"], score=float(variant["score"]),
            )
            db.add(row); db.flush(); ids.append(row.id)
        db.commit()
    return {"created": len(ids), "draft_ids": ids, "variants": variants}


# ── Tracking / scheduling / attribution ───────────────────────────────
@app.post("/api/v1/threads/tracking-links", status_code=201)
def make_tracking_link(body: TrackingLinkRequest, request: Request) -> dict[str, Any]:
    row = create_tracking_link(body.product_id, body.platform, body.destination_url, body.campaign_key, body.channel)
    public_base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
    return {"id": row.id, "code": row.code, "url": f"{public_base}/t/{row.code}"}


@app.get("/t/{code}")
def tracking_redirect(code: str, request: Request):
    xff = request.headers.get("x-forwarded-for", "")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "")
    try:
        link, click = record_click(
            code=code, ip=ip, user_agent=request.headers.get("user-agent", ""),
            referer=request.headers.get("referer", ""), hash_salt=os.getenv("TRACKING_HASH_SALT", "autoseller"),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="tracking link not found")
    response = RedirectResponse(link.destination_url, status_code=302)
    response.set_cookie("as_click", click.click_id, max_age=604800, httponly=True, secure=request.url.scheme == "https", samesite="lax")
    return response


@app.post("/api/v1/threads/schedules", status_code=201)
def schedule_post(body: ScheduleRequest) -> dict[str, Any]:
    scheduled_utc = _to_utc_naive(body.scheduled_at)
    if scheduled_utc <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="scheduled_at must be in the future")
    media_type = body.media_type.upper().strip()
    if media_type not in {"TEXT", "IMAGE", "VIDEO", "CAROUSEL"}:
        raise HTTPException(status_code=400, detail="invalid media_type")
    if media_type in {"IMAGE", "VIDEO"} and not body.media_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="media_url must be a public HTTP(S) URL")
    if media_type == "CAROUSEL" and not 2 <= len(body.carousel_items) <= 20:
        raise HTTPException(status_code=400, detail="carousel requires 2 to 20 items")
    with get_db() as db:
        if not db.get(Product, body.product_id):
            raise HTTPException(status_code=404, detail="product not found")
        if body.draft_id and not db.get(SocialContentDraft, body.draft_id):
            raise HTTPException(status_code=404, detail="draft not found")
        if body.tracking_link_id and not db.get(TrackingLink, body.tracking_link_id):
            raise HTTPException(status_code=404, detail="tracking link not found")
        row = ScheduledSocialPost(
            draft_id=body.draft_id, product_id=body.product_id, content=body.content,
            scheduled_at=scheduled_utc, campaign_key=body.campaign_key, cta_keyword=body.cta_keyword,
            tracking_link_id=body.tracking_link_id, media_type=media_type, media_url=body.media_url,
            alt_text=body.alt_text, carousel_items_json=json.dumps(body.carousel_items, ensure_ascii=False),
        )
        db.add(row)
        if body.draft_id:
            draft = db.get(SocialContentDraft, body.draft_id)
            if draft:
                draft.status = "scheduled"; draft.tracking_link_id = body.tracking_link_id
        db.commit(); db.refresh(row)
        return {"id": row.id, "status": row.status, "media_type": row.media_type, "scheduled_at_utc": row.scheduled_at.isoformat()}


@app.get("/api/v1/threads/schedules")
def list_schedules(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    with get_db() as db:
        rows = list(db.scalars(select(ScheduledSocialPost).order_by(desc(ScheduledSocialPost.scheduled_at)).limit(limit)).all())
    return [{
        "id": r.id, "product_id": r.product_id, "content": r.content, "campaign_key": r.campaign_key,
        "media_type": r.media_type, "media_url": r.media_url, "scheduled_at_utc": r.scheduled_at.isoformat(),
        "status": r.status, "threads_post_id": r.threads_post_id, "error": r.error,
    } for r in rows]


@app.post("/api/v1/attribution/run")
def run_attribution(window_hours: int = Query(default=72, ge=1, le=720), force: bool = False) -> dict[str, Any]:
    return {**attribute_recent_orders(window_hours=window_hours, force=force), "summary": attribution_summary()}


@app.get("/api/v1/attribution")
def list_attribution(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    with get_db() as db:
        rows = list(db.scalars(select(OrderAttribution).order_by(desc(OrderAttribution.attributed_at)).limit(limit)).all())
    return {"summary": attribution_summary(), "items": [{
        "id": r.id, "platform": r.platform, "platform_order_id": r.platform_order_id,
        "product_id": r.product_id, "campaign_key": r.campaign_key, "type": r.attribution_type,
        "confidence": r.confidence, "order_amount": r.order_amount, "reason": r.reason,
        "attributed_at": r.attributed_at.isoformat(),
    } for r in rows]}


# ── Sales Inbox ───────────────────────────────────────────────────────
@app.get("/api/v1/threads/comments")
def list_comments(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    with get_db() as db:
        rows = db.scalars(select(ThreadsComment).order_by(desc(ThreadsComment.received_at)).limit(limit)).all()
        return [{
            "id": row.id, "threads_comment_id": row.threads_comment_id, "threads_post_id": row.threads_post_id,
            "username": row.author_username, "text": row.comment_text, "intent": row.intent,
            "purchase_intent": row.purchase_intent_score, "requires_human": row.requires_human,
            "processed": row.processed, "received_at": row.received_at.isoformat(),
        } for row in rows]


@app.get("/api/v1/threads/leads")
def hot_leads(min_score: float = Query(default=0.7, ge=0, le=1), limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    with get_db() as db:
        rows = db.scalars(
            select(ThreadsComment).where(ThreadsComment.purchase_intent_score >= min_score)
            .order_by(desc(ThreadsComment.purchase_intent_score), desc(ThreadsComment.received_at)).limit(limit)
        ).all()
        return [{
            "id": row.id, "username": row.author_username, "text": row.comment_text,
            "intent": row.intent, "purchase_intent": row.purchase_intent_score,
            "requires_human": row.requires_human,
        } for row in rows]


@app.post("/api/v1/threads/rules", status_code=201)
def create_rule(body: RuleRequest) -> dict[str, Any]:
    with get_db() as db:
        existing = db.scalar(select(ThreadsAutomationRule).where(ThreadsAutomationRule.keyword == body.keyword))
        if existing:
            raise HTTPException(status_code=409, detail="keyword already exists")
        rule = ThreadsAutomationRule(**body.model_dump())
        db.add(rule); db.commit(); db.refresh(rule)
        return {"id": rule.id, "keyword": rule.keyword, "enabled": rule.enabled}


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return value.astimezone(timezone.utc).replace(tzinfo=None)
