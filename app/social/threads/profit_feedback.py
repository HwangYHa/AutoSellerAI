from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from app.db import Order, PlatformOrder, Product, get_db
from app.social.threads.growth_models import OrderAttribution, ScheduledSocialPost, SocialContentDraft, TrackingClick, TrackingLink
from app.social.threads.models import ThreadsPost
from app.social.threads.profit_models import ContentProfitSnapshot, ContentStrategyProfile


def _fee_rate(platform: str) -> float:
    env = {
        "smartstore": "SMARTSTORE_DEFAULT_FEE_RATE",
        "coupang": "COUPANG_DEFAULT_FEE_RATE",
    }.get(platform, "")
    default = 0.055 if platform == "smartstore" else 0.108
    try:
        return max(0.0, min(float(os.getenv(env, str(default))), 0.5))
    except Exception:
        return default


def _fallback_shipping_cost() -> float:
    try:
        return max(0.0, float(os.getenv("SOCIAL_DEFAULT_SHIPPING_COST", "3000")))
    except Exception:
        return 3000.0


def _find_finance_order(db, po: PlatformOrder) -> Order | None:
    return db.scalar(
        select(Order)
        .where(Order.platform == po.platform, Order.platform_order_id == po.platform_order_id)
        .order_by(desc(Order.ordered_at))
    )


def _order_finance(db, attribution: OrderAttribution) -> dict[str, Any]:
    po = db.get(PlatformOrder, attribution.platform_order_row_id)
    if not po:
        return {"quality": "estimated", "revenue": attribution.order_amount, "supply": 0.0, "fee": 0.0,
                "shipping": 0.0, "ad": 0.0, "return": 0.0, "vat": 0.0, "profit": 0.0,
                "cancelled": 0, "returned": 0}

    finance = _find_finance_order(db, po)
    if finance:
        cancelled = 1 if finance.status == "cancelled" else 0
        returned = 1 if finance.status == "returned" else 0
        return {
            "quality": "actual",
            "revenue": float(finance.gross_revenue or 0.0),
            "supply": float(finance.supply_cost or 0.0),
            "fee": float(finance.platform_fee or 0.0),
            "shipping": float(finance.net_shipping_cost or 0.0),
            "ad": float(finance.ad_cost or 0.0),
            "return": float(finance.return_cost or 0.0),
            "vat": float(finance.vat_payable or 0.0),
            "profit": float(finance.net_profit or 0.0),
            "cancelled": cancelled,
            "returned": returned,
        }

    product = db.get(Product, po.product_id) if po.product_id else None
    qty = max(1, int(po.quantity or 1))
    revenue = float(po.unit_price or 0.0) * qty
    supply = float(product.supply_price if product else 0.0) * qty
    fee = revenue * _fee_rate(po.platform)
    cancelled = 1 if po.status == "cancelled" else 0
    returned = 1 if po.status == "returned" else 0
    if cancelled:
        revenue = 0.0
    shipping = _fallback_shipping_cost() if revenue > 0 else 0.0
    return_cost = _fallback_shipping_cost() * 2 if returned else 0.0
    profit = revenue - supply - fee - shipping - return_cost
    return {
        "quality": "estimated",
        "revenue": revenue,
        "supply": supply,
        "fee": fee,
        "shipping": shipping,
        "ad": 0.0,
        "return": return_cost,
        "vat": 0.0,
        "profit": profit,
        "cancelled": cancelled,
        "returned": returned,
    }


def _score(metrics: dict[str, float | int]) -> tuple[float, dict[str, float]]:
    clicks = max(0, int(metrics.get("clicks", 0)))
    orders = max(0, int(metrics.get("orders", 0)))
    profit = float(metrics.get("profit", 0.0))
    revenue = max(0.0, float(metrics.get("revenue", 0.0)))
    avg_conf = max(0.0, min(float(metrics.get("confidence", 0.0)), 1.0))
    returns = max(0, int(metrics.get("returns", 0)))

    margin = profit / revenue if revenue > 0 else 0.0
    cvr = orders / clicks if clicks > 0 else 0.0
    return_rate = returns / orders if orders > 0 else 0.0
    ppc = profit / clicks if clicks > 0 else 0.0

    margin_score = max(0.0, min((margin + 0.05) / 0.35, 1.0)) * 100
    total_profit_score = max(0.0, min(math.log1p(max(profit, 0.0)) / math.log1p(300000.0), 1.0)) * 100
    ppc_score = max(0.0, min(ppc / 1500.0, 1.0)) * 100
    cvr_score = max(0.0, min(cvr / 0.08, 1.0)) * 100
    confidence_score = avg_conf * 100
    return_score = max(0.0, 1.0 - min(return_rate / 0.2, 1.0)) * 100

    raw = (
        margin_score * 0.25
        + total_profit_score * 0.25
        + ppc_score * 0.20
        + cvr_score * 0.15
        + confidence_score * 0.10
        + return_score * 0.05
    )

    # 소표본 과적합 방지: 주문 10건/클릭 100건 전까지 중립값 50으로 수축.
    maturity = min(1.0, max(orders / 10.0, clicks / 100.0))
    final = 50.0 + (raw - 50.0) * maturity
    if profit < 0:
        final = min(final, 35.0)

    breakdown = {
        "margin": round(margin_score, 2),
        "total_profit": round(total_profit_score, 2),
        "profit_per_click": round(ppc_score, 2),
        "conversion": round(cvr_score, 2),
        "attribution_confidence": round(confidence_score, 2),
        "return_quality": round(return_score, 2),
        "sample_maturity": round(maturity * 100, 2),
    }
    return round(max(0.0, min(final, 100.0)), 2), breakdown


def rebuild_profit_feedback() -> dict[str, int]:
    """현재 Tracking/Attribution/Order 데이터로 게시물·캠페인 손익 스냅샷을 재구축한다."""
    with get_db() as db:
        links = list(db.scalars(select(TrackingLink)).all())
        clicks_by_link = defaultdict(int)
        for c in db.scalars(select(TrackingClick)).all():
            clicks_by_link[c.tracking_link_id] += 1

        attrs = [a for a in db.scalars(select(OrderAttribution)).all() if a.attribution_type != "unattributed"]
        attrs_by_link: dict[int, list[OrderAttribution]] = defaultdict(list)
        for a in attrs:
            if a.tracking_link_id:
                attrs_by_link[a.tracking_link_id].append(a)

        # 가장 최근 스냅샷 세트만 유지한다.
        db.query(ContentProfitSnapshot).delete()
        db.flush()

        post_groups: dict[int, dict[str, Any]] = {}
        campaign_groups: dict[str, dict[str, Any]] = {}

        for link in links:
            finance_rows = [_order_finance(db, a) for a in attrs_by_link.get(link.id, [])]
            common = {
                "clicks": clicks_by_link.get(link.id, 0),
                "attrs": attrs_by_link.get(link.id, []),
                "finance": finance_rows,
                "link": link,
            }
            if link.post_id:
                g = post_groups.setdefault(link.post_id, {"clicks": 0, "attrs": [], "finance": [], "links": []})
                g["clicks"] += common["clicks"]
                g["attrs"].extend(common["attrs"])
                g["finance"].extend(finance_rows)
                g["links"].append(link)
            if link.campaign_key:
                g = campaign_groups.setdefault(link.campaign_key, {"clicks": 0, "attrs": [], "finance": [], "links": []})
                g["clicks"] += common["clicks"]
                g["attrs"].extend(common["attrs"])
                g["finance"].extend(finance_rows)
                g["links"].append(link)

        created = 0
        for post_id, g in post_groups.items():
            post = db.get(ThreadsPost, post_id)
            if not post:
                continue
            angle = _resolve_angle_for_post(db, post)
            row = _snapshot_from_group("post", str(post_id), g, post=post, angle=angle)
            db.add(row)
            created += 1

        for campaign_key, g in campaign_groups.items():
            row = _snapshot_from_group("campaign", campaign_key, g)
            db.add(row)
            created += 1

        db.commit()

    profiles = rebuild_strategy_profiles()
    return {"snapshots": created, "profiles": profiles}


def _resolve_angle_for_post(db, post: ThreadsPost) -> str:
    sched = db.scalar(
        select(ScheduledSocialPost)
        .where(ScheduledSocialPost.threads_post_id == post.threads_post_id)
        .order_by(desc(ScheduledSocialPost.published_at))
    )
    if sched and sched.draft_id:
        draft = db.get(SocialContentDraft, sched.draft_id)
        if draft:
            return draft.angle or ""
    return ""


def _snapshot_from_group(scope_type: str, scope_key: str, g: dict[str, Any],
                         post: ThreadsPost | None = None, angle: str = "") -> ContentProfitSnapshot:
    attrs: list[OrderAttribution] = g["attrs"]
    finance: list[dict[str, Any]] = g["finance"]
    clicks = int(g["clicks"])
    orders = len(attrs)
    gross = sum(x["revenue"] for x in finance)
    supply = sum(x["supply"] for x in finance)
    fee = sum(x["fee"] for x in finance)
    shipping = sum(x["shipping"] for x in finance)
    ad = sum(x["ad"] for x in finance)
    ret_cost = sum(x["return"] for x in finance)
    vat = sum(x["vat"] for x in finance)
    profit = sum(x["profit"] for x in finance)
    cancelled = sum(x["cancelled"] for x in finance)
    returned = sum(x["returned"] for x in finance)
    confidence = sum(a.confidence for a in attrs) / orders if orders else 0.0
    deterministic = sum(1 for a in attrs if a.attribution_type == "deterministic")
    qualities = {x["quality"] for x in finance}
    quality = "actual" if qualities == {"actual"} and qualities else "mixed" if "actual" in qualities else "estimated"
    metrics = {"clicks": clicks, "orders": orders, "profit": profit, "revenue": gross,
               "confidence": confidence, "returns": returned + cancelled}
    score, breakdown = _score(metrics)
    campaign = post.campaign_key if post else (g["links"][0].campaign_key if g["links"] else scope_key)
    product_id = post.product_id if post else (g["links"][0].product_id if g["links"] else None)
    return ContentProfitSnapshot(
        scope_type=scope_type, scope_key=scope_key,
        post_id=post.id if post else None,
        threads_post_id=post.threads_post_id if post else "",
        campaign_key=campaign or "", product_id=product_id,
        content_angle=angle, clicks=clicks, attributed_orders=orders,
        deterministic_orders=deterministic, cancelled_orders=cancelled, returned_orders=returned,
        gross_revenue=gross, supply_cost=supply, platform_fee=fee,
        shipping_cost=shipping, ad_cost=ad, return_cost=ret_cost, vat_payable=vat,
        net_profit=profit, net_margin_rate=(profit / gross if gross else 0.0),
        conversion_rate=(orders / clicks if clicks else 0.0),
        return_rate=((returned + cancelled) / orders if orders else 0.0),
        profit_per_click=(profit / clicks if clicks else 0.0),
        profit_per_order=(profit / orders if orders else 0.0),
        avg_attribution_confidence=confidence,
        content_score=score, score_breakdown=json.dumps(breakdown, ensure_ascii=False),
        finance_quality=quality, calculated_at=datetime.utcnow(),
    )


def rebuild_strategy_profiles() -> int:
    with get_db() as db:
        rows = list(db.scalars(select(ContentProfitSnapshot).where(ContentProfitSnapshot.scope_type == "post")).all())
        db.query(ContentStrategyProfile).delete()
        by_product: dict[int, list[ContentProfitSnapshot]] = defaultdict(list)
        for row in rows:
            if row.product_id:
                by_product[row.product_id].append(row)

        created = 0
        for product_id, items in by_product.items():
            product = db.get(Product, product_id)
            angles: dict[str, list[ContentProfitSnapshot]] = defaultdict(list)
            for item in items:
                if item.content_angle:
                    angles[item.content_angle].append(item)
            ranking = []
            for angle, vals in angles.items():
                orders = sum(v.attributed_orders for v in vals)
                profit = sum(v.net_profit for v in vals)
                avg_score = sum(v.content_score for v in vals) / len(vals)
                ranking.append({"angle": angle, "score": round(avg_score, 2), "orders": orders, "profit": round(profit, 2)})
            ranking.sort(key=lambda x: (x["profit"], x["score"]), reverse=True)
            preferred = [x["angle"] for x in ranking if x["orders"] >= 2 and x["profit"] > 0][:3]
            avoid = [x["angle"] for x in reversed(ranking) if x["orders"] >= 2 and x["profit"] <= 0][:2]
            row = ContentStrategyProfile(
                profile_key=f"product:{product_id}", product_id=product_id,
                category=(product.category if product else ""),
                preferred_angles_json=json.dumps(preferred, ensure_ascii=False),
                avoid_angles_json=json.dumps(avoid, ensure_ascii=False),
                winning_patterns_json=json.dumps(ranking[:5], ensure_ascii=False),
                evidence_json=json.dumps({"ranking": ranking}, ensure_ascii=False),
                sample_posts=len(items), sample_orders=sum(v.attributed_orders for v in items),
                total_net_profit=sum(v.net_profit for v in items),
                avg_content_score=(sum(v.content_score for v in items) / len(items) if items else 0.0),
            )
            db.add(row)
            created += 1
        db.commit()
        return created


def learning_context(product_id: int) -> dict[str, Any]:
    with get_db() as db:
        profile = db.scalar(select(ContentStrategyProfile).where(ContentStrategyProfile.profile_key == f"product:{product_id}"))
        if not profile or not profile.auto_apply:
            return {}
        return {
            "preferred_angles": json.loads(profile.preferred_angles_json or "[]"),
            "avoid_angles": json.loads(profile.avoid_angles_json or "[]"),
            "winning_patterns": json.loads(profile.winning_patterns_json or "[]"),
            "sample_posts": profile.sample_posts,
            "sample_orders": profile.sample_orders,
            "total_net_profit": profile.total_net_profit,
            "avg_content_score": profile.avg_content_score,
        }


def profit_dashboard(limit: int = 50) -> dict[str, Any]:
    with get_db() as db:
        rows = list(db.scalars(
            select(ContentProfitSnapshot)
            .where(ContentProfitSnapshot.scope_type == "post")
            .order_by(desc(ContentProfitSnapshot.net_profit), desc(ContentProfitSnapshot.content_score))
            .limit(limit)
        ).all())
    return {
        "total_net_profit": sum(r.net_profit for r in rows),
        "total_revenue": sum(r.gross_revenue for r in rows),
        "total_clicks": sum(r.clicks for r in rows),
        "total_orders": sum(r.attributed_orders for r in rows),
        "items": [
            {
                "post_id": r.post_id, "threads_post_id": r.threads_post_id,
                "campaign_key": r.campaign_key, "product_id": r.product_id,
                "angle": r.content_angle, "clicks": r.clicks,
                "orders": r.attributed_orders, "revenue": r.gross_revenue,
                "supply_cost": r.supply_cost, "platform_fee": r.platform_fee,
                "shipping_cost": r.shipping_cost, "ad_cost": r.ad_cost,
                "return_cost": r.return_cost, "returns": r.returned_orders + r.cancelled_orders,
                "net_profit": r.net_profit, "margin_rate": r.net_margin_rate,
                "content_score": r.content_score, "finance_quality": r.finance_quality,
            }
            for r in rows
        ],
    }
