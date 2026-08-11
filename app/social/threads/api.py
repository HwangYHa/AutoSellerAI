from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from app.db import get_db, init_db
from app.social.threads import models as _models  # register SQLAlchemy metadata
from app.social.threads.client import ThreadsClient, ThreadsConfig, verify_webhook_signature
from app.social.threads.models import ThreadsAutomationRule, ThreadsComment, ThreadsPost
from app.social.threads.tasks import enqueue_webhook_event


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


app = FastAPI(title="AutoSellerAI Social Commerce API", version="0.1.0")


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
