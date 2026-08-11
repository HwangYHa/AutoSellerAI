from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.db import Product, get_db
from app.social.threads.ai_agent import classify_and_draft
from app.social.threads.client import ThreadsClient
from app.social.threads.models import ThreadsAutomationRule, ThreadsComment, ThreadsPost, ThreadsReply


def _extract_comment(event: dict[str, Any]) -> dict[str, str] | None:
    """Normalize common Threads webhook shapes without coupling the app to one payload revision."""
    candidates: list[dict[str, Any]] = []
    if isinstance(event, dict):
        candidates.append(event)
        for key in ("value", "data", "changes", "entry"):
            value = event.get(key)
            if isinstance(value, dict):
                candidates.append(value)
            elif isinstance(value, list):
                candidates.extend(x for x in value if isinstance(x, dict))

    for item in candidates:
        value = item.get("value") if isinstance(item.get("value"), dict) else item
        comment_id = value.get("id") or value.get("reply_id") or value.get("comment_id")
        text = value.get("text") or value.get("message")
        post_id = value.get("media_id") or value.get("post_id") or value.get("parent_id") or ""
        if comment_id and text:
            return {
                "comment_id": str(comment_id),
                "post_id": str(post_id),
                "text": str(text),
                "author_id": str(value.get("from", {}).get("id", "") if isinstance(value.get("from"), dict) else value.get("user_id", "")),
                "username": str(value.get("username", "")),
            }
    return None


def process_event(event: dict[str, Any], auto_reply: bool = True) -> dict[str, Any]:
    normalized = _extract_comment(event)
    if not normalized:
        return {"status": "ignored", "reason": "unsupported_event"}

    with get_db() as db:
        existing = db.scalar(select(ThreadsComment).where(ThreadsComment.threads_comment_id == normalized["comment_id"]))
        if existing:
            return {"status": "duplicate", "comment_id": existing.id}

        comment = ThreadsComment(
            threads_comment_id=normalized["comment_id"],
            threads_post_id=normalized["post_id"],
            author_id=normalized["author_id"],
            author_username=normalized["username"],
            comment_text=normalized["text"],
        )
        db.add(comment)
        db.flush()

        post = None
        if normalized["post_id"]:
            post = db.scalar(select(ThreadsPost).where(ThreadsPost.threads_post_id == normalized["post_id"]))

        product = None
        product_context = None
        if post and post.product_id:
            product = db.get(Product, post.product_id)
            if product:
                product_context = {
                    "id": product.id,
                    "name": product.name,
                    "sell_price": product.sell_price,
                    "category": product.category,
                    "brand": product.brand,
                    "origin": product.origin,
                    "material": product.material,
                }

        result = _rule_reply(db, normalized["text"], post.product_id if post else None)
        if result is None:
            result = classify_and_draft(normalized["text"], product_context)

        comment.intent = result["intent"]
        comment.purchase_intent_score = float(result["purchase_intent"])
        comment.sentiment = result.get("sentiment", "neutral")
        comment.requires_human = bool(result.get("requires_human", False))
        comment.processed = True
        comment.processed_at = datetime.utcnow()

        reply = ThreadsReply(
            comment_id=comment.id,
            reply_text=_policy_filter(result.get("reply", "")),
            source=result.get("source", "rule"),
            status="human_review" if comment.requires_human else "pending",
        )
        db.add(reply)
        db.commit()
        db.refresh(reply)

        if auto_reply and not comment.requires_human and reply.reply_text:
            try:
                remote_id = ThreadsClient().publish_text(reply.reply_text, reply_to_id=comment.threads_comment_id)
                with get_db() as write_db:
                    persisted = write_db.get(ThreadsReply, reply.id)
                    if persisted:
                        persisted.threads_reply_id = remote_id
                        persisted.status = "sent"
                        persisted.sent_at = datetime.utcnow()
                        write_db.commit()
                return {"status": "replied", "comment_id": comment.id, "reply_id": remote_id, "intent": comment.intent}
            except Exception as exc:
                with get_db() as write_db:
                    persisted = write_db.get(ThreadsReply, reply.id)
                    if persisted:
                        persisted.status = "failed"
                        persisted.error = str(exc)[:1000]
                        write_db.commit()
                return {"status": "reply_failed", "comment_id": comment.id, "error": str(exc)}

        return {"status": reply.status, "comment_id": comment.id, "intent": comment.intent, "purchase_intent": comment.purchase_intent_score}


def _rule_reply(db, text: str, product_id: int | None) -> dict[str, Any] | None:
    normalized = text.strip().lower()
    rules = db.scalars(
        select(ThreadsAutomationRule)
        .where(ThreadsAutomationRule.enabled.is_(True))
        .order_by(ThreadsAutomationRule.priority.asc())
    ).all()
    for rule in rules:
        if rule.product_id not in (None, product_id):
            continue
        if rule.keyword.strip().lower() in normalized:
            return {
                "intent": "KEYWORD_TRIGGER",
                "purchase_intent": 0.65,
                "sentiment": "neutral",
                "requires_human": False,
                "reply": rule.reply_template,
                "source": "rule",
            }
    return None


def _policy_filter(text: str) -> str:
    text = " ".join((text or "").split()).strip()
    if not text:
        return ""
    # Keep public replies concise and avoid accidental secret exposure.
    blocked = ("THREADS_ACCESS_TOKEN", "CLAUDE_API_KEY", "NAVER_CLIENT_SECRET", "COUPANG_SECRET_KEY")
    if any(token in text.upper() for token in blocked):
        return "자동 답변을 생성하지 못했습니다. 담당자 확인이 필요합니다."
    return text[:450]
