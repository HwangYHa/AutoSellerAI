from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy import select

from app.db import get_db, init_db
from app.social.threads.client import ThreadsClient
from app.social.threads.growth_models import ScheduledSocialPost, SocialContentDraft, TrackingLink
from app.social.threads.models import ThreadsPost

logger = logging.getLogger(__name__)


def publish_due_posts(limit: int = 20) -> dict[str, int]:
    init_db()
    now = datetime.utcnow()
    result = {"published": 0, "failed": 0, "claimed": 0}

    with get_db() as db:
        due = list(
            db.scalars(
                select(ScheduledSocialPost)
                .where(
                    ScheduledSocialPost.status == "scheduled",
                    ScheduledSocialPost.scheduled_at <= now,
                )
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
                content = row.content
                product_id = row.product_id
                campaign_key = row.campaign_key
                cta_keyword = row.cta_keyword
                draft_id = row.draft_id
                tracking_link_id = row.tracking_link_id

            remote_id = ThreadsClient().publish_text(content)

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


def run_scheduler_loop(interval_seconds: int = 20) -> None:
    interval_seconds = max(5, min(int(interval_seconds), 300))
    logger.info("Threads scheduler started interval=%ss", interval_seconds)
    while True:
        try:
            publish_due_posts()
        except Exception:
            logger.exception("Threads scheduler cycle failed")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_scheduler_loop()
