from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, select

from app.db import PlatformOrder, get_db
from app.social.threads.growth_models import OrderAttribution, TrackingClick, TrackingLink


def create_tracking_link(product_id: int, platform: str, destination_url: str,
                         campaign_key: str = "", channel: str = "threads") -> TrackingLink:
    platform = platform.strip().lower()
    if platform not in {"smartstore", "coupang"}:
        raise ValueError("platform must be smartstore or coupang")
    if not destination_url.startswith(("https://", "http://")):
        raise ValueError("destination_url must be an absolute http(s) URL")

    with get_db() as db:
        for _ in range(10):
            code = secrets.token_urlsafe(7).replace("-", "").replace("_", "")[:10]
            exists = db.scalar(select(TrackingLink).where(TrackingLink.code == code))
            if not exists:
                row = TrackingLink(
                    code=code,
                    product_id=product_id,
                    platform=platform,
                    destination_url=destination_url,
                    campaign_key=campaign_key.strip(),
                    channel=channel,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                db.expunge(row)
                return row
    raise RuntimeError("failed to allocate tracking code")


def record_click(code: str, ip: str = "", user_agent: str = "", referer: str = "",
                 hash_salt: str = "") -> tuple[TrackingLink, TrackingClick]:
    with get_db() as db:
        link = db.scalar(select(TrackingLink).where(TrackingLink.code == code, TrackingLink.active.is_(True)))
        if not link:
            raise LookupError("tracking link not found")
        click_id = secrets.token_hex(12)
        raw_ip = (ip or "").strip()
        ip_hash = hashlib.sha256(f"{hash_salt}:{raw_ip}".encode("utf-8")).hexdigest() if raw_ip else ""
        click = TrackingClick(
            tracking_link_id=link.id,
            click_id=click_id,
            ip_hash=ip_hash,
            user_agent=(user_agent or "")[:500],
            referer=(referer or "")[:2000],
        )
        db.add(click)
        db.commit()
        db.refresh(click)
        db.expunge(link)
        db.expunge(click)
        return link, click


def attribute_recent_orders(window_hours: int = 72, force: bool = False) -> dict[str, int]:
    window_hours = max(1, min(int(window_hours), 24 * 30))
    stats = {"attributed": 0, "unattributed": 0, "skipped": 0}

    with get_db() as db:
        orders = list(db.scalars(select(PlatformOrder).order_by(desc(PlatformOrder.ordered_at)).limit(5000)).all())
        for order in orders:
            existing = db.scalar(
                select(OrderAttribution).where(OrderAttribution.platform_order_row_id == order.id)
            )
            if existing and not force:
                stats["skipped"] += 1
                continue
            if existing and force:
                db.delete(existing)
                db.flush()

            attribution = _attribute_one(db, order, window_hours)
            db.add(attribution)
            if attribution.attribution_type == "unattributed":
                stats["unattributed"] += 1
            else:
                stats["attributed"] += 1
        db.commit()
    return stats


def _attribute_one(db, order: PlatformOrder, window_hours: int) -> OrderAttribution:
    amount = float(order.unit_price or 0.0) * int(order.quantity or 1)
    base = dict(
        platform_order_row_id=order.id,
        platform=order.platform,
        platform_order_id=order.platform_order_id,
        product_id=int(order.product_id or 0),
        order_amount=amount,
    )
    if not order.product_id:
        return OrderAttribution(**base, attribution_type="unattributed", confidence=0.0,
                                reason="내부 product_id가 연결되지 않은 주문")

    start = order.ordered_at - timedelta(hours=window_hours)
    candidates = list(
        db.execute(
            select(TrackingClick, TrackingLink)
            .join(TrackingLink, TrackingClick.tracking_link_id == TrackingLink.id)
            .where(
                TrackingLink.product_id == order.product_id,
                TrackingLink.platform == order.platform,
                TrackingClick.clicked_at <= order.ordered_at,
                TrackingClick.clicked_at >= start,
            )
            .order_by(desc(TrackingClick.clicked_at))
        ).all()
    )
    if not candidates:
        return OrderAttribution(**base, attribution_type="unattributed", confidence=0.0,
                                reason=f"주문 전 {window_hours}시간 내 동일 상품/플랫폼 클릭 없음")

    click, link = candidates[0]
    gap_hours = max(0.0, (order.ordered_at - click.clicked_at).total_seconds() / 3600.0)
    if gap_hours <= 1:
        confidence = 0.92
    elif gap_hours <= 6:
        confidence = 0.86
    elif gap_hours <= 24:
        confidence = 0.76
    else:
        confidence = 0.62

    # 여러 캠페인 클릭이 경쟁하면 확신도를 낮춘다.
    unique_links = {row[1].id for row in candidates}
    if len(unique_links) > 1:
        confidence = max(0.45, confidence - min(0.20, 0.05 * (len(unique_links) - 1)))

    reason = (
        f"동일 product_id/platform의 가장 최근 클릭과 주문 연결; "
        f"클릭→주문 {gap_hours:.1f}시간, 후보 클릭 {len(candidates)}건, 캠페인 {len(unique_links)}개"
    )
    return OrderAttribution(
        **base,
        tracking_link_id=link.id,
        click_id=click.click_id,
        campaign_key=link.campaign_key,
        channel=link.channel,
        attribution_type="probabilistic",
        confidence=confidence,
        reason=reason,
    )


def attribution_summary() -> dict[str, Any]:
    with get_db() as db:
        rows = list(db.scalars(select(OrderAttribution)).all())
    total_orders = len(rows)
    attributed = [r for r in rows if r.attribution_type != "unattributed"]
    revenue = sum(r.order_amount for r in attributed)
    avg_conf = sum(r.confidence for r in attributed) / len(attributed) if attributed else 0.0
    return {
        "orders": total_orders,
        "attributed_orders": len(attributed),
        "attributed_revenue": revenue,
        "avg_confidence": avg_conf,
    }
