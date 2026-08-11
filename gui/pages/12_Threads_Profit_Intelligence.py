"""스레드 수익 인텔리전스 — 순이익 기반 콘텐츠 점수 / 전략 피드백."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
from sqlalchemy import desc, select

from app.db import Product, get_db, init_db
from app.social.threads.profit_feedback import profit_dashboard, rebuild_profit_feedback
from app.social.threads.profit_models import ContentProfitSnapshot, ContentStrategyProfile
from gui.ui_ko import angle_label, finance_quality_label

st.set_page_config(page_title="스레드 수익 인텔리전스 | AutoSeller AI", page_icon="💹", layout="wide")
init_db()

st.markdown("# 💹 스레드 수익 인텔리전스")
st.caption("조회수가 아니라 실제 귀속 순이익을 기준으로 게시물·캠페인을 평가하고 다음 AI 콘텐츠 전략에 반영합니다.")

c1, c2 = st.columns([1, 4])
if c1.button("🔄 손익·점수 재계산", type="primary", use_container_width=True):
    with st.spinner("구매 귀속·정산 데이터를 기반으로 다시 계산 중..."):
        result = rebuild_profit_feedback()
    st.success(f"손익 스냅샷 {result['snapshots']}건 / 전략 프로필 {result['profiles']}건 갱신")
    st.rerun()
c2.info("예약 실행 서비스도 기본 15분마다 자동 갱신합니다. 실제 정산 주문 데이터가 있으면 실제 순이익을 우선 사용하고, 없을 때만 보수적으로 추정합니다.")

summary = profit_dashboard(200)
k1, k2, k3, k4 = st.columns(4)
k1.metric("귀속 매출", f"{summary['total_revenue']:,.0f}원")
k2.metric("실제/추정 순이익", f"{summary['total_net_profit']:,.0f}원")
k3.metric("추적 클릭", f"{summary['total_clicks']:,}")
k4.metric("귀속 주문", f"{summary['total_orders']:,}")

post_tab, campaign_tab, strategy_tab = st.tabs(["🧵 게시물별 순이익", "🎯 캠페인별 순이익", "🧠 AI 전략 학습"])

with post_tab:
    rows = summary["items"]
    if not rows:
        st.info("아직 계산 가능한 게시물 손익 데이터가 없습니다. 추적 클릭과 귀속 주문이 쌓이면 자동 생성됩니다.")
    else:
        st.dataframe([
            {
                "스레드 게시물 ID": r["threads_post_id"],
                "캠페인": r["campaign_key"],
                "콘텐츠 유형": angle_label(r["angle"]),
                "클릭": r["clicks"],
                "주문": r["orders"],
                "매출": round(r["revenue"]),
                "공급가": round(r["supply_cost"]),
                "수수료": round(r["platform_fee"]),
                "배송/반품": round(r["shipping_cost"] + r["return_cost"]),
                "반품/취소": r["returns"],
                "순이익": round(r["net_profit"]),
                "순이익률": f"{r['margin_rate']*100:.1f}%",
                "콘텐츠 점수": f"{r['content_score']:.1f}",
                "정산 품질": finance_quality_label(r["finance_quality"]),
            }
            for r in rows
        ], use_container_width=True, hide_index=True)

        best = max(rows, key=lambda x: x["net_profit"])
        st.success(
            f"현재 순이익 1위: 스레드 {best['threads_post_id'] or best['post_id']} · "
            f"순이익 {best['net_profit']:,.0f}원 · 콘텐츠 점수 {best['content_score']:.1f}"
        )

with campaign_tab:
    with get_db() as db:
        campaigns = list(db.scalars(
            select(ContentProfitSnapshot)
            .where(ContentProfitSnapshot.scope_type == "campaign")
            .order_by(desc(ContentProfitSnapshot.net_profit))
        ).all())
    if not campaigns:
        st.info("캠페인 데이터가 없습니다.")
    else:
        st.dataframe([
            {
                "캠페인": r.campaign_key or r.scope_key,
                "클릭": r.clicks,
                "주문": r.attributed_orders,
                "매출": round(r.gross_revenue),
                "순이익": round(r.net_profit),
                "순이익률": f"{r.net_margin_rate*100:.1f}%",
                "전환율": f"{r.conversion_rate*100:.2f}%",
                "반품률": f"{r.return_rate*100:.1f}%",
                "클릭당 순이익": f"{r.profit_per_click:,.0f}원",
                "콘텐츠 점수": f"{r.content_score:.1f}",
                "정산 품질": finance_quality_label(r.finance_quality),
            }
            for r in campaigns
        ], use_container_width=True, hide_index=True)

with strategy_tab:
    with get_db() as db:
        profiles = list(db.scalars(select(ContentStrategyProfile).order_by(desc(ContentStrategyProfile.total_net_profit))).all())
        product_ids = [p.product_id for p in profiles if p.product_id]
        products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(product_ids))).all()} if product_ids else {}

    if not profiles:
        st.info("아직 AI가 학습할 만큼 수익성 데이터가 없습니다. 최소 몇 건의 귀속 주문이 쌓인 뒤 전략 프로필이 생성됩니다.")
    else:
        for p in profiles:
            product = products.get(p.product_id)
            preferred = json.loads(p.preferred_angles_json or "[]")
            avoid = json.loads(p.avoid_angles_json or "[]")
            patterns = json.loads(p.winning_patterns_json or "[]")
            with st.expander(f"{product.name if product else p.profile_key} · 누적 순이익 {p.total_net_profit:,.0f}원", expanded=False):
                a, b, c, d = st.columns(4)
                a.metric("학습 게시물", p.sample_posts)
                b.metric("귀속 주문", p.sample_orders)
                c.metric("평균 콘텐츠 점수", f"{p.avg_content_score:.1f}")
                d.metric("자동 적용", "켜짐" if p.auto_apply else "꺼짐")
                st.write("**우선 콘텐츠 유형:**", ", ".join(angle_label(x) for x in preferred) if preferred else "아직 없음")
                st.write("**회피 콘텐츠 유형:**", ", ".join(angle_label(x) for x in avoid) if avoid else "아직 없음")
                if patterns:
                    translated_patterns = [
                        {
                            "콘텐츠 유형": angle_label(row.get("angle")),
                            "평균 점수": row.get("score"),
                            "주문": row.get("orders"),
                            "순이익": row.get("profit"),
                        }
                        for row in patterns
                    ]
                    st.dataframe(translated_patterns, use_container_width=True, hide_index=True)
                st.caption("다음 AI 콘텐츠 생성 시 이 프로필이 자동으로 프롬프트에 반영됩니다. 주문 표본이 적으면 과적합 방지를 위해 영향력이 제한됩니다.")
