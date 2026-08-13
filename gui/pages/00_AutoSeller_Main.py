"""AutoSellerAI Seller OS v2 — 단일 운영 제어센터.

기존 legacy_app.py의 다중 탭 화면을 정상 운영 경로에서 제거하고
상품 / 주문·배송 / 수익 / 연동·시스템 네 영역으로 통합한다.
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
from sqlalchemy import func

from app.db import Listing, Order, PlatformOrder, Product, SettlementPeriod, get_db, init_db
from app.orchestration.oneclick import get_next_stage, get_process_status
from app.pipeline import collect_platform_orders, register_invoice_to_platform
from app.policies.runtime_patch import apply_fulfillment_policy_patch
from gui.korean_runtime import apply_korean_patch
from gui.product_workspace import render_product_workspace

apply_korean_patch()
apply_fulfillment_policy_patch()
init_db()

st.set_page_config(
    page_title="Seller OS | 오토셀러 AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container{max-width:1240px;padding-top:1.4rem;padding-bottom:5rem}
    .seller-hero{padding:22px 26px;border:1px solid #e2e8f0;border-radius:18px;
      background:linear-gradient(135deg,#0f172a,#1e293b 60%,#312e81);color:white;margin-bottom:16px}
    .seller-hero h1{font-size:26px;margin:0;font-weight:800}.seller-hero p{margin:6px 0 0;color:#cbd5e1}
    [data-testid="stMetric"]{background:#fff;border:1px solid #e2e8f0;padding:12px;border-radius:12px}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="seller-hero">
      <h1>⚡ Seller OS</h1>
      <p>오늘 처리할 일부터 상품·주문·배송·수익까지 한 화면 규칙으로 관리합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

status = get_process_status()
next_stage = get_next_stage(status)
counts = status.get("counts", {})

# 상단에는 '현재 상황 + 다음 행동'만 보여준다.
q1, q2, q3, q4 = st.columns([1.1, 1.1, 1.1, 2.2])
q1.metric("상품", counts.get("products", 0))
q2.metric("판매중", counts.get("listed_products", 0))
q3.metric("주문", counts.get("platform_orders", 0))
with q4:
    if next_stage:
        st.info(f"**다음 작업 {next_stage['order']:02d}. {next_stage['title']}**\n\n{next_stage['description']}")
    else:
        st.success("필수 운영 단계가 모두 완료 상태입니다.")

# 업무 목적 기준 4개 탭만 유지한다.
tab_products, tab_orders, tab_profit, tab_system = st.tabs([
    "📦 상품",
    "🚚 주문 · 배송",
    "💰 수익",
    "🔌 연동 · 시스템",
])

with tab_products:
    render_product_workspace()

with tab_orders:
    st.markdown("### 🚚 주문 · 배송")
    st.caption("주문 수집 → 공급처 확인/발주 → 송장 등록의 순서로 봅니다. 재고·발주서 같은 내부 기능은 실제 위탁 주문 흐름과 분리합니다.")

    a, b, c = st.columns([1.3, 1.3, 3.4])
    hours = a.selectbox("수집 범위", [3, 12, 24, 72, 168], index=2, format_func=lambda x: f"최근 {x}시간")
    if b.button("🔄 신규 주문 수집", type="primary", use_container_width=True):
        with st.spinner("쿠팡·스마트스토어 주문을 확인 중..."):
            try:
                result = collect_platform_orders(hours_back=int(hours))
                st.success("주문 수집 완료")
                st.json(result, expanded=False)
            except Exception as exc:
                st.error(f"주문 수집 실패: {exc}")
    c.info("실제 공급처 발주는 비용이 발생하므로 자동으로 실행하지 않습니다. 신규 주문을 먼저 확인한 뒤 발주/송장을 처리합니다.")

    with get_db() as db:
        orders = db.query(PlatformOrder).order_by(PlatformOrder.ordered_at.desc()).limit(100).all()

    if not orders:
        st.info("수집된 주문이 없습니다.")
    else:
        status_filter = st.selectbox("주문 상태", ["전체", "new", "fulfilling", "shipped", "completed", "cancelled"])
        visible = [o for o in orders if status_filter == "전체" or o.status == status_filter]
        for order in visible:
            with st.container(border=True):
                left, center, right = st.columns([1.1, 4.3, 1.6], vertical_alignment="center")
                left.markdown(f"**{order.platform.upper()}**")
                left.caption(order.status)
                center.markdown(f"**{order.product_name or '상품명 미확인'}**")
                center.caption(
                    f"주문 {order.platform_order_id} · 수량 {order.quantity} · "
                    f"수취인 {order.receiver_name or '-'} · {order.ordered_at.strftime('%Y-%m-%d %H:%M') if order.ordered_at else ''}"
                )
                if order.tracking_number:
                    center.write(f"📦 {order.delivery_company or '-'} · {order.tracking_number}")
                right.write("송장등록 완료" if order.invoice_registered else "송장 대기")

                with st.expander("주문 처리"):
                    st.write(f"배송지: {order.shipping_address or '-'}")
                    st.write(f"배송메모: {order.shipping_message or '-'}")
                    st.write(f"공급처: {order.supplier or '-'} · 공급처 주문번호: {order.supplier_order_id or '-'}")
                    if not order.invoice_registered:
                        dc, tn, submit = st.columns([1.2, 2.0, 1.0])
                        delivery_company = dc.text_input("택배사 코드", value=order.delivery_company or "", key=f"dc_{order.id}")
                        tracking = tn.text_input("운송장 번호", value=order.tracking_number or "", key=f"tn_{order.id}")
                        if submit.button("송장 등록", key=f"invoice_{order.id}", use_container_width=True):
                            if not delivery_company.strip() or not tracking.strip():
                                st.warning("택배사 코드와 운송장 번호를 입력하세요.")
                            else:
                                result = register_invoice_to_platform(order.id, delivery_company.strip(), tracking.strip())
                                if result.get("ok"):
                                    st.success("판매채널 송장 등록 완료")
                                    st.rerun()
                                else:
                                    st.error(result.get("error", "송장 등록 실패"))

with tab_profit:
    st.markdown("### 💰 수익")
    st.caption("상품관리 화면에서 판단해야 할 것은 예상마진, 여기서는 실제 주문·정산 결과만 봅니다.")
    with get_db() as db:
        order_count = db.query(Order).count()
        revenue = float(db.query(func.coalesce(func.sum(Order.gross_revenue), 0)).scalar() or 0)
        profit = float(db.query(func.coalesce(func.sum(Order.net_profit), 0)).scalar() or 0)
        platform_fee = float(db.query(func.coalesce(func.sum(Order.platform_fee), 0)).scalar() or 0)
        ad_cost = float(db.query(func.coalesce(func.sum(Order.ad_cost), 0)).scalar() or 0)
        settlements = db.query(SettlementPeriod).order_by(SettlementPeriod.period_end.desc()).limit(30).all()

    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("정산 주문", order_count)
    p2.metric("매출", f"{revenue:,.0f}원")
    p3.metric("순이익", f"{profit:,.0f}원")
    p4.metric("플랫폼 수수료", f"{platform_fee:,.0f}원")
    p5.metric("광고비", f"{ad_cost:,.0f}원")

    if settlements:
        st.dataframe([
            {
                "기간": x.period_label,
                "채널": x.platform,
                "주문": x.order_count,
                "매출": float(x.gross_revenue or 0),
                "공급가": float(x.supply_cost or 0),
                "수수료": float(x.platform_fee or 0),
                "배송비": float(x.shipping_cost or 0),
                "광고비": float(x.ad_cost or 0),
                "순이익": float(x.net_profit or 0),
            }
            for x in settlements
        ], use_container_width=True, hide_index=True)
    else:
        st.info("아직 생성된 정산 기간이 없습니다.")

with tab_system:
    st.markdown("### 🔌 연동 · 시스템")
    st.caption("평소에는 이 화면을 건드릴 필요가 없습니다. 인증 변경이나 오류가 있을 때만 들어옵니다.")

    checks = status.get("connections", {}).get("checks", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("스마트스토어", "설정됨" if checks.get("smartstore") else "확인 필요")
    c2.metric("쿠팡", "설정됨" if checks.get("coupang") else "확인 필요")
    c3.metric("오너클랜", "설정됨" if checks.get("ownerclan") else "확인 필요")
    c4.metric("AI", "설정됨" if checks.get("ai") else "확인 필요")

    st.markdown("#### 필요한 설정 화면")
    l1, l2, l3, l4 = st.columns(4)
    l1.page_link("pages/05_판매채널_상품동기화.py", label="판매채널 동기화", icon="🔄", use_container_width=True)
    l2.page_link("pages/20_오너클랜_연동.py", label="오너클랜", icon="🏬", use_container_width=True)
    l3.page_link("pages/21_도매꾹_연동.py", label="도매꾹", icon="🏷️", use_container_width=True)
    l4.page_link("pages/22_온채널_연동.py", label="온채널", icon="🛍️", use_container_width=True)

    st.markdown("#### 전체 자동화")
    st.page_link("pages/01_원큐_운영.py", label="🚀 원큐 운영 상태와 다음 단계 보기", use_container_width=True)
