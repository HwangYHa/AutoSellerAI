from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db import Order, PlatformOrder, Product, get_db, init_db
from app.social.threads.content_engine import generate_threads_content
from app.social.threads.growth_models import ScheduledSocialPost, TrackingClick, TrackingLink
from app.social.threads.models import ThreadsPost
from app.social.threads.profit_feedback import learning_context, rebuild_profit_feedback
from app.social.threads.profit_models import ContentProfitSnapshot, ContentStrategyProfile
from app.social.threads.tracking import attribute_recent_orders
from app.social.threads.growth_models import SocialContentDraft


def test_tracking_order_settlement_profit_feedback_changes_next_angle():
    """End-to-end synthetic validation of the closed-loop profit feedback path.

    One order is intentionally not enough to auto-switch strategy. The current
    production guard requires >=3 attributed orders before generate_threads_content
    replaces the default angle with the learned preferred angle. This test creates
    three real DB order/settlement rows so the final strategy transition is testable.
    """
    init_db()
    suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    base = datetime.utcnow() - timedelta(hours=1)

    with get_db() as db:
        product = Product(
            sku=f"CI-PROFIT-{suffix}",
            source="onchannel",
            source_id=f"src-{suffix}",
            name="CI 차량용 청소기",
            supply_price=15500,
            sell_price=29900,
            category="자동차용품",
            status="listed",
        )
        db.add(product)
        db.flush()

        draft = SocialContentDraft(
            product_id=product.id,
            angle="question",
            body="차량 청소할 때 어디가 가장 불편한가요?",
            cta_keyword="청소기",
            target_platform="smartstore",
            status="published",
        )
        db.add(draft)
        db.flush()

        post = ThreadsPost(
            threads_post_id=f"threads-ci-{suffix}",
            product_id=product.id,
            campaign_key=f"ci-profit-{suffix}",
            content=draft.body,
            cta_keyword="청소기",
            status="published",
            published_at=base,
        )
        db.add(post)
        db.flush()

        schedule = ScheduledSocialPost(
            draft_id=draft.id,
            product_id=product.id,
            content=draft.body,
            campaign_key=post.campaign_key,
            cta_keyword="청소기",
            scheduled_at=base - timedelta(minutes=5),
            status="published",
            threads_post_id=post.threads_post_id,
            published_at=base,
        )
        db.add(schedule)

        link = TrackingLink(
            code=f"ci{suffix[-8:]}",
            product_id=product.id,
            platform="smartstore",
            destination_url="https://smartstore.naver.com/example/products/1",
            campaign_key=post.campaign_key,
            post_id=post.id,
            active=True,
        )
        db.add(link)
        db.flush()

        # Three separate clicks/orders provide enough evidence for auto-application.
        for i in range(3):
            click_time = base + timedelta(minutes=i * 10)
            order_time = click_time + timedelta(minutes=3)
            db.add(TrackingClick(
                tracking_link_id=link.id,
                click_id=f"click-{suffix}-{i}",
                ip_hash="ci",
                user_agent="pytest",
                referer="https://www.threads.net/",
                clicked_at=click_time,
            ))

            platform_order_id = f"NAVER-CI-{suffix}-{i}"
            po = PlatformOrder(
                platform="smartstore",
                platform_order_id=platform_order_id,
                platform_item_id=f"item-{i}",
                origin_product_no="origin-ci",
                product_id=product.id,
                product_name=product.name,
                quantity=1,
                unit_price=29900,
                status="completed",
                ordered_at=order_time,
            )
            db.add(po)

            # Existing settlement Order is the financial source of truth.
            db.add(Order(
                product_id=product.id,
                platform="smartstore",
                platform_order_id=platform_order_id,
                quantity=1,
                unit_sale_price=29900,
                unit_supply_price=15500,
                shipping_fee_paid=3000,
                shipping_fee_charged=0,
                platform_fee_rate=0.055,
                platform_fee=1644.5,
                ad_cost=0,
                return_cost=0,
                gross_revenue=29900,
                supply_cost=15500,
                net_shipping_cost=3000,
                gross_profit=9760.5,
                vat_payable=0,
                net_profit=9760.5,
                margin_rate=9760.5 / 29900,
                status="completed",
                ordered_at=order_time,
                settled_at=order_time + timedelta(minutes=1),
            ))

        product_id = product.id
        post_id = post.id
        db.commit()

    attr = attribute_recent_orders(window_hours=72, force=False)
    assert attr["attributed"] >= 3

    rebuilt = rebuild_profit_feedback()
    assert rebuilt["snapshots"] >= 2  # post + campaign
    assert rebuilt["profiles"] >= 1

    with get_db() as db:
        snapshot = db.scalar(select(ContentProfitSnapshot).where(
            ContentProfitSnapshot.scope_type == "post",
            ContentProfitSnapshot.post_id == post_id,
        ))
        assert snapshot is not None
        assert snapshot.attributed_orders == 3
        assert snapshot.gross_revenue == 89700
        assert snapshot.supply_cost == 46500
        assert round(snapshot.platform_fee, 1) == 4933.5
        assert snapshot.shipping_cost == 9000
        assert round(snapshot.net_profit, 1) == 29281.5
        assert snapshot.finance_quality == "actual"
        assert snapshot.content_angle == "question"
        assert snapshot.content_score > 50

        profile = db.scalar(select(ContentStrategyProfile).where(
            ContentStrategyProfile.profile_key == f"product:{product_id}"
        ))
        assert profile is not None
        assert profile.sample_orders == 3
        assert "question" in json.loads(profile.preferred_angles_json)

    context = learning_context(product_id)
    assert context["sample_orders"] == 3
    assert context["preferred_angles"][0] == "question"

    generated = generate_threads_content(
        {"id": product_id, "name": "CI 차량용 청소기", "category": "자동차용품", "sell_price": 29900},
        angle="problem_solution",
        cta_keyword="청소기",
        count=1,
    )
    assert generated[0]["selected_angle"] == "question"
    assert "profit_feedback" in generated[0]["source"]
