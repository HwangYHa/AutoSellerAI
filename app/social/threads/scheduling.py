from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime

from sqlalchemy import select

from app.db import get_db, init_db
from app.social.threads.auth import credential_status, refresh_stored_credential
from app.social.threads.client import ThreadsClient
from app.social.threads.growth_models import ScheduledSocialPost, SocialContentDraft, TrackingLink
from app.social.threads.models import ThreadsPost
from app.social.threads.profit_feedback import rebuild_profit_feedback
from app.social.threads.tracking import attribute_recent_orders

logger = logging.getLogger(__name__)


def _publish_row(row: ScheduledSocialPost) -> str:
    client = ThreadsClient()
    media_type = (row.media_type or "TEXT").upper()
    if media_type == "TEXT":
        return client.publish_text(row.content)
    if media_type == "IMAGE":
        return client.publish_image(row.media_url, row.content, row.alt_text)
    if media_type == "VIDEO":
        return client.publish_video(row.media_url, row.content, row.alt_text)
    if media_type == "CAROUSEL":
        items = json.loads(row.carousel_items_json or "[]")
        return client.publish_carousel(items, row.content)
    raise ValueError(f"unsupported Threads media_type: {media_type}")


def publish_due_posts(limit: int = 20) -> dict[str, int]:
    init_db()
    now = datetime.utcnow()
    result = {"published": 0, "failed": 0, "claimed": 0}

    with get_db() as db:
        due = list(
            db.scalars(
                select(ScheduledSocialPost)
                .where(ScheduledSocialPost.status == "scheduled", ScheduledSocialPost.scheduled_at <= now)
                .order_by(ScheduledSocialPost.scheduled_at.asc())
                .limit(max(1, min(limit, 100)))
            ).all()
        )
        ids = []
        for row in due:
            row.status = "publishing"
            row.error = ""
            ids.append(row.id)
        db.commit()
        result["claimed"] = len(ids)

    for schedule_id in ids:
        try:
            with get_db() as db:
                row = db.get(ScheduledSocialPost, schedule_id)
                if not row or row.status != "publishing":
                    continue
                product_id = row.product_id
                campaign_key = row.campaign_key
                cta_keyword = row.cta_keyword
                draft_id = row.draft_id
                tracking_link_id = row.tracking_link_id
                remote_id = _publish_row(row)
                content = row.content

            with get_db() as db:
                row = db.get(ScheduledSocialPost, schedule_id)
                if not row:
                    continue
                post = ThreadsPost(
                    threads_post_id=remote_id,
                    product_id=product_id,
                    campaign_key=campaign_key,
                    content=content,
                    cta_keyword=cta_keyword,
                    status="published",
                )
                db.add(post)
                db.flush()
                row.status = "published"
                row.threads_post_id = remote_id
                row.published_at = datetime.utcnow()
                row.error = ""
                if draft_id:
                    draft = db.get(SocialContentDraft, draft_id)
                    if draft:
                        draft.status = "published"
                if tracking_link_id:
                    link = db.get(TrackingLink, tracking_link_id)
                    if link:
                        link.post_id = post.id
                db.commit()
            result["published"] += 1
        except Exception as exc:
            logger.exception("scheduled Threads publish failed: %s", schedule_id)
            with get_db() as db:
                row = db.get(ScheduledSocialPost, schedule_id)
                if row:
                    row.status = "failed"
                    row.error = str(exc)[:2000]
                    db.commit()
            result["failed"] += 1
    return result


def refresh_token_if_needed(threshold_days: int = 7) -> dict:
    status = credential_status()
    if not status.get("connected"):
        return {"refreshed": False, "reason": "not_connected"}
    remaining = status.get("days_remaining")
    if remaining is None or remaining > threshold_days:
        return {"refreshed": False, "reason": "not_due", "days_remaining": remaining}
    refreshed = refresh_stored_credential(status.get("id"))
    return {"refreshed": True, "days_remaining": refreshed.get("days_remaining")}


def run_scheduler_loop(interval_seconds: int = 20) -> None:
    interval_seconds = max(5, min(int(interval_seconds), 300))
    attr_enabled = os.getenv("ATTRIBUTION_AUTO_ENABLED", "true").lower() == "true"
    attr_every = max(60, int(os.getenv("ATTRIBUTION_RUN_INTERVAL_SECONDS", "300")))
    attr_window = max(1, min(int(os.getenv("ATTRIBUTION_WINDOW_HOURS", "72")), 720))
    profit_enabled = os.getenv("CONTENT_PROFIT_FEEDBACK_ENABLED", "true").lower() == "true"
    profit_every = max(300, int(os.getenv("CONTENT_PROFIT_FEEDBACK_INTERVAL_SECONDS", "900")))
    token_every = max(3600, int(os.getenv("THREADS_TOKEN_CHECK_INTERVAL_SECONDS", "21600")))
    token_threshold = max(1, min(int(os.getenv("THREADS_TOKEN_REFRESH_THRESHOLD_DAYS", "7")), 30))
    last_attr = 0.0
    last_profit = 0.0
    last_token = 0.0

    logger.info(
        "Threads scheduler started interval=%ss attribution=%s/%ss profit-feedback=%s/%ss token-check=%ss",
        interval_seconds, attr_enabled, attr_every, profit_enabled, profit_every, token_every,
    )
    while True:
        try:
            publish_due_posts()
        except Exception:
            logger.exception("Threads scheduler publish cycle failed")

        now_mono = time.monotonic()
        if attr_enabled and now_mono - last_attr >= attr_every:
            try:
                logger.info("order attribution cycle: %s", attribute_recent_orders(window_hours=attr_window, force=False))
            except Exception:
                logger.exception("Threads attribution cycle failed")
            finally:
                last_attr = now_mono

        if profit_enabled and now_mono - last_profit >= profit_every:
            try:
                logger.info("content profit feedback cycle: %s", rebuild_profit_feedback())
            except Exception:
                logger.exception("Threads content profit feedback cycle failed")
            finally:
                last_profit = now_mono

        if now_mono - last_token >= token_every:
            try:
                logger.info("Threads token lifecycle cycle: %s", refresh_token_if_needed(token_threshold))
            except Exception:
                logger.exception("Threads token refresh cycle failed")
            finally:
                last_token = now_mono

        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_scheduler_loop()
