"""AutoSellerAI — Threads content, scheduling, tracking and attribution UI."""
from __future__ import annotations

import os
from datetime import datetime, time as dt_time, timezone
from zoneinfo import ZoneInfo

import streamlit as st
from sqlalchemy import desc, func, select

from app.db import PlatformOrder, Product, get_db, init_db
from app.social.threads import growth_models as _growth_models  # register metadata
from app.social.threads.content_engine import ANGLES, generate_threads_content
from app.social.threads.growth_models import (
    OrderAttribution,
    ScheduledSocialPost,
    SocialContentDraft,
    TrackingClick,
    TrackingLink,
)
from app.social.threads.tracking import attribute_recent_orders, attribution_summary, create_tracking_link


KST = ZoneInfo("Asia/Seoul")
st.set_page_config(
    page_title="Threads Growth Automation | AutoSeller AI",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)
init_db()

st.markdown(
    """
    <style>
    .block-container{padding-top:1.3rem;max-width:1420px}
    .growth-hero{background:linear-gradient(135deg,#111827,#0F766E 58%,#059669);color:#fff;padding:24px 28px;border-radius:18px;margin-bottom:18px;box-shadow:0 12px 34px rgba(5,150,105,.18)}
    .growth-hero h2{margin:0;font-size:24px;font-weight:800}.growth-hero p{margin:6px 0 0;color:rgba(255,255,255,.72);font-size:13px}
    .kpi{background:#fff;border:1px solid #E2E8F0;border-radius:14px;padding:15px}.kpi-label{font-size:11px;font-weight:700;color:#94A3B8;text-transform:uppercase}.kpi-value{font-size:25px;font-weight:800;color:#0F172A;margin-top:4px}
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("## 🛒 Social Commerce")
st.sidebar.markdown("**🚀 Threads Growth Automation**")
st.sidebar.caption("AI 콘텐츠 → 예약 → 클릭 → 주문 귀속")

st.markdown(
    """
    <div class="growth-hero">
      <h2>🚀 Threads Growth Automation</h2>
      <p>AutoSellerAI 상품을 Threads 콘텐츠로 만들고, 예약 발행하고, Tracking URL 클릭과 네이버·쿠팡 실제 주문을 연결합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def _products() -> list[Product]:
    with get_db() as db:
        return list(db.scalars(select(Product).order_by(desc(Product.updated_at)).limit(2000)).all())


def _product_label(p: Product) -> str:
    return f"#{p.id} · {p.name[:55]} · {p.sell_price:,.0f}원"


def _public_tracking_url(code: str) -> str:
    base = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/t/{code}"


def _kst_to_utc_naive(day, clock) -> datetime:
    local = datetime.combine(day, clock).replace(tzinfo=KST)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_to_kst(value: datetime | None) -> str:
    if value is None:
        return "-"
    aware = value.replace(tzinfo=timezone.utc)
    return aware.astimezone(KST).strftime("%Y-%m-%d %H:%M")


products = _products()
product_map = {p.id: p for p in products}

with get_db() as db:
    draft_count = int(db.scalar(select(func.count()).select_from(SocialContentDraft)) or 0)
    scheduled_count = int(db.scalar(select(func.count()).select_from(ScheduledSocialPost).where(ScheduledSocialPost.status == "scheduled")) or 0)
    click_count = int(db.scalar(select(func.count()).select_from(TrackingClick)) or 0)
summary = attribution_summary()

k1, k2, k3, k4, k5 = st.columns(5)
for col, label, value in [
    (k1, "콘텐츠 초안", draft_count),
    (k2, "예약 대기", scheduled_count),
    (k3, "Tracking 클릭", click_count),
    (k4, "귀속 주문", summary["attributed_orders"]),
    (k5, "귀속 매출", f"{summary['attributed_revenue']:,.0f}원"),
]:
    with col:
        st.markdown(f'<div class="kpi"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>', unsafe_allow_html=True)

(tab_ai, tab_track, tab_schedule, tab_attr) = st.tabs([
    "✨ AI 콘텐츠 자동 생성",
    "🔗 Tracking URL",
    "🗓️ 게시 예약",
    "📈 구매 Attribution",
])


# ─────────────────────────────────────────────────────────────────────
# AI Content
# ─────────────────────────────────────────────────────────────────────
with tab_ai:
    st.subheader("AI Threads 콘텐츠 생성")
    if not products:
        st.warning("먼저 상품을 수집/등록해야 합니다.")
    else:
        left, right = st.columns([0.9, 1.3], gap="large")
        with left:
            pid = st.selectbox("상품", [p.id for p in products], format_func=lambda x: _product_label(product_map[x]), key="growth_ai_product")
            angle = st.selectbox("콘텐츠 각도", list(ANGLES.keys()), format_func=lambda x: ANGLES[x])
            cta = st.text_input("CTA 댓글 키워드", placeholder="청소기")
            target_platform = st.radio("최종 판매처", ["smartstore", "coupang"], horizontal=True, format_func=lambda x: "네이버 스마트스토어" if x == "smartstore" else "쿠팡")
            target_url = st.text_input("실제 상품 URL", placeholder="https://smartstore.naver.com/... 또는 https://www.coupang.com/...")
            count = st.slider("후보 수", 1, 5, 3)
            if st.button("✨ AI 콘텐츠 생성", type="primary", use_container_width=True):
                p = product_map[pid]
                context = {
                    "id": p.id, "name": p.name, "category": p.category, "brand": p.brand,
                    "origin": p.origin, "material": p.material, "sell_price": p.sell_price,
                }
                with st.spinner("상품 데이터를 바탕으로 콘텐츠 생성 중..."):
                    variants = generate_threads_content(context, angle, cta, count)
                    with get_db() as db:
                        for v in variants:
                            db.add(SocialContentDraft(
                                product_id=pid,
                                angle=angle,
                                body=v["body"],
                                cta_keyword=v["cta_keyword"],
                                target_platform=target_platform,
                                target_url=target_url.strip(),
                                ai_source=v["source"],
                                score=float(v["score"]),
                            ))
                        db.commit()
                st.success(f"콘텐츠 후보 {len(variants)}개를 생성했습니다.")
                st.rerun()

        with right:
            st.markdown("#### 최근 생성 초안")
            with get_db() as db:
                drafts = list(db.scalars(select(SocialContentDraft).order_by(desc(SocialContentDraft.created_at)).limit(30)).all())
            if not drafts:
                st.info("아직 생성된 초안이 없습니다.")
            for d in drafts:
                p = product_map.get(d.product_id)
                with st.container(border=True):
                    a, b = st.columns([4, 1])
                    a.markdown(f"**{p.name if p else f'상품 #{d.product_id}'}**")
                    b.metric("AI Score", f"{d.score:.0f}")
                    st.write(d.body)
                    st.caption(f"{ANGLES.get(d.angle, d.angle)} · CTA `{d.cta_keyword or '-'}` · {d.target_platform} · {d.ai_source} · {d.status}")


# ─────────────────────────────────────────────────────────────────────
# Tracking URLs
# ─────────────────────────────────────────────────────────────────────
with tab_track:
    st.subheader("Tracking URL")
    st.caption("외부 마켓으로 보내기 직전에 AutoSellerAI redirect를 거쳐 클릭 이벤트를 남깁니다. IP는 원문 대신 일방향 해시만 저장합니다.")
    left, right = st.columns([0.9, 1.35], gap="large")
    with left:
        if products:
            tpid = st.selectbox("상품", [p.id for p in products], format_func=lambda x: _product_label(product_map[x]), key="tracking_product")
            platform = st.radio("판매처", ["smartstore", "coupang"], horizontal=True, key="tracking_platform", format_func=lambda x: "네이버" if x == "smartstore" else "쿠팡")
            destination = st.text_input("목적지 상품 URL", key="tracking_destination")
            campaign = st.text_input("Campaign Key", placeholder="threads-car-cleaner-202608", key="tracking_campaign")
            if st.button("🔗 Tracking URL 생성", type="primary", use_container_width=True):
                try:
                    row = create_tracking_link(tpid, platform, destination.strip(), campaign.strip())
                    st.success(_public_tracking_url(row.code))
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with right:
        with get_db() as db:
            links = list(db.scalars(select(TrackingLink).order_by(desc(TrackingLink.created_at)).limit(100)).all())
            click_counts = dict(db.execute(select(TrackingClick.tracking_link_id, func.count()).group_by(TrackingClick.tracking_link_id)).all())
        if not links:
            st.info("Tracking URL이 없습니다.")
        else:
            st.dataframe([
                {
                    "ID": l.id,
                    "상품": product_map[l.product_id].name[:28] if l.product_id in product_map else l.product_id,
                    "플랫폼": l.platform,
                    "Campaign": l.campaign_key,
                    "Tracking URL": _public_tracking_url(l.code),
                    "클릭": click_counts.get(l.id, 0),
                    "활성": "✅" if l.active else "OFF",
                }
                for l in links
            ], use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────
# Scheduling
# ─────────────────────────────────────────────────────────────────────
with tab_schedule:
    st.subheader("Threads 예약 게시")
    left, right = st.columns([0.95, 1.35], gap="large")
    with left:
        with get_db() as db:
            draft_rows = list(db.scalars(select(SocialContentDraft).where(SocialContentDraft.status.in_(["draft", "approved"])).order_by(desc(SocialContentDraft.created_at)).limit(200)).all())
            link_rows = list(db.scalars(select(TrackingLink).where(TrackingLink.active.is_(True)).order_by(desc(TrackingLink.created_at)).limit(200)).all())
        if not draft_rows:
            st.info("먼저 AI 콘텐츠 초안을 생성하세요.")
        else:
            draft_id = st.selectbox("콘텐츠 초안", [d.id for d in draft_rows], format_func=lambda x: f"#{x} · {next(d.body for d in draft_rows if d.id == x)[:55]}")
            selected = next(d for d in draft_rows if d.id == draft_id)
            edited_body = st.text_area("게시 본문", value=selected.body, max_chars=500, height=180)
            link_options = [None] + [l.id for l in link_rows if l.product_id == selected.product_id]
            tracking_link_id = st.selectbox("연결 Tracking URL", link_options, format_func=lambda x: "연결 안 함" if x is None else f"#{x} · {_public_tracking_url(next(l.code for l in link_rows if l.id == x))}")
            campaign_key = st.text_input("Campaign Key", value=(next((l.campaign_key for l in link_rows if l.id == tracking_link_id), "") if tracking_link_id else ""), key="schedule_campaign")
            cta_keyword = st.text_input("CTA 키워드", value=selected.cta_keyword, key="schedule_cta")
            dcol, tcol = st.columns(2)
            schedule_day = dcol.date_input("게시 날짜", value=datetime.now(KST).date())
            schedule_clock = tcol.time_input("게시 시각(KST)", value=dt_time(19, 0))
            if st.button("🗓️ 예약 등록", type="primary", use_container_width=True):
                scheduled_utc = _kst_to_utc_naive(schedule_day, schedule_clock)
                if scheduled_utc <= datetime.utcnow():
                    st.error("현재 이후 시각을 선택하세요.")
                else:
                    with get_db() as db:
                        row = ScheduledSocialPost(
                            draft_id=selected.id,
                            product_id=selected.product_id,
                            content=edited_body.strip(),
                            campaign_key=campaign_key.strip(),
                            cta_keyword=cta_keyword.strip(),
                            tracking_link_id=tracking_link_id,
                            scheduled_at=scheduled_utc,
                        )
                        db.add(row)
                        draft = db.get(SocialContentDraft, selected.id)
                        if draft:
                            draft.status = "scheduled"
                            draft.tracking_link_id = tracking_link_id
                        db.commit()
                    st.success("예약 등록 완료")
                    st.rerun()

    with right:
        with get_db() as db:
            schedules = list(db.scalars(select(ScheduledSocialPost).order_by(desc(ScheduledSocialPost.scheduled_at)).limit(100)).all())
        if not schedules:
            st.info("예약 게시물이 없습니다.")
        else:
            st.dataframe([
                {
                    "ID": s.id,
                    "상품": product_map[s.product_id].name[:28] if s.product_id in product_map else s.product_id,
                    "예약(KST)": _utc_to_kst(s.scheduled_at),
                    "상태": s.status,
                    "Campaign": s.campaign_key,
                    "Threads ID": s.threads_post_id or "-",
                    "오류": s.error[:80] if s.error else "",
                }
                for s in schedules
            ], use_container_width=True, hide_index=True)
        st.caption("Docker의 `threads-scheduler`가 예약시각을 확인해 자동 발행합니다. DB에는 UTC로 저장하고 화면에는 KST로 표시합니다.")


# ─────────────────────────────────────────────────────────────────────
# Attribution
# ─────────────────────────────────────────────────────────────────────
with tab_attr:
    st.subheader("네이버·쿠팡 실제 구매 Attribution")
    st.warning("외부 마켓 주문 API는 AutoSellerAI의 click_id를 주문에 반환하지 않습니다. 따라서 현재 자동 귀속은 실제 주문 데이터에 대해 동일 상품·플랫폼·클릭 후 주문시간을 이용한 확률적 Attribution이며, 운영자가 검증한 건만 '확정'으로 승격할 수 있습니다.")

    x1, x2, x3 = st.columns([1, 1, 2])
    lookback = x1.number_input("귀속 윈도우(시간)", min_value=1, max_value=720, value=int(os.getenv("ATTRIBUTION_WINDOW_HOURS", "72")))
    force = x2.checkbox("기존 결과 재계산")
    if x3.button("📈 실제 주문 귀속 계산", type="primary", use_container_width=True):
        with st.spinner("PlatformOrder와 Tracking Click을 비교 중..."):
            result = attribute_recent_orders(int(lookback), force=force)
        st.success(f"귀속 {result['attributed']}건 · 미귀속 {result['unattributed']}건 · 건너뜀 {result['skipped']}건")
        st.rerun()

    s = attribution_summary()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("분석 주문", f"{s['orders']}건")
    m2.metric("귀속 주문", f"{s['attributed_orders']}건")
    m3.metric("귀속 매출", f"{s['attributed_revenue']:,.0f}원")
    m4.metric("평균 신뢰도", f"{s['avg_confidence']*100:.1f}%")

    with get_db() as db:
        attrs = list(db.scalars(select(OrderAttribution).order_by(desc(OrderAttribution.attributed_at)).limit(300)).all())
        order_map = {o.id: o for o in db.scalars(select(PlatformOrder).limit(5000)).all()}

    if not attrs:
        st.info("아직 Attribution 결과가 없습니다. 먼저 네이버/쿠팡 주문 수집이 완료되어야 합니다.")
    else:
        for a in attrs:
            order = order_map.get(a.platform_order_row_id)
            icon = "✅" if a.attribution_type == "deterministic" else "🟡" if a.attribution_type == "probabilistic" else "⚪"
            with st.expander(f"{icon} {a.platform.upper()} · 주문 {a.platform_order_id} · {a.order_amount:,.0f}원 · 신뢰도 {a.confidence*100:.0f}%"):
                st.write(f"상품: {order.product_name if order else f'#{a.product_id}'}")
                st.write(f"Campaign: `{a.campaign_key or '-'}` · 방식: **{a.attribution_type}**")
                st.caption(a.reason)
                if a.attribution_type == "probabilistic":
                    if st.button("✅ 운영자 확인 — 확정 귀속", key=f"confirm_attr_{a.id}"):
                        with get_db() as db:
                            row = db.get(OrderAttribution, a.id)
                            if row:
                                row.attribution_type = "deterministic"
                                row.confidence = 1.0
                                row.reason = "운영자 검토 후 확정 · " + row.reason
                                db.commit()
                        st.rerun()
