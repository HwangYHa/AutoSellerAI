"""AutoSeller AI — application hub.

The legacy all-in-one Streamlit workspace is preserved as a page while this
entrypoint exposes explicit operating areas, including Social Commerce → Threads.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="AutoSeller AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 2rem;}
    .hub-hero {background:linear-gradient(135deg,#111827,#312E81 55%,#6D28D9);color:#fff;
      border-radius:20px;padding:28px 32px;margin-bottom:22px;box-shadow:0 16px 44px rgba(49,46,129,.2)}
    .hub-hero h1{margin:0;font-size:30px;font-weight:850}.hub-hero p{margin:8px 0 0;color:rgba(255,255,255,.7)}
    .area{border:1px solid #E2E8F0;border-radius:16px;padding:18px;background:#fff;margin-bottom:14px}
    .area h3{margin:0 0 6px}.muted{color:#64748B;font-size:13px}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hub-hero">
      <h1>⚡ AutoSeller AI</h1>
      <p>상품 수집·등록·주문 운영과 AI 소셜커머스를 하나의 Seller OS에서 관리합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("## AutoSeller AI")
st.sidebar.caption("Seller OS Navigation")
st.sidebar.markdown("### 🧭 운영")
st.sidebar.page_link("pages/00_AutoSeller_Main.py", label="통합 운영 화면", icon="⚡")
st.sidebar.markdown("### 🛒 소셜커머스")
st.sidebar.page_link("pages/10_Social_Commerce_Threads.py", label="Threads", icon="🧵")
st.sidebar.page_link("pages/11_Threads_Growth_Automation.py", label="Growth Automation", icon="📈")
st.sidebar.markdown("---")
st.sidebar.caption("Threads: 콘텐츠 → 게시 → 댓글 영업 → 클릭 → 구매 귀속")

left, right = st.columns(2, gap="large")
with left:
    st.markdown('<div class="area"><h3>⚡ 통합 운영</h3><div class="muted">기존 AutoSellerAI의 대시보드, 파이프라인, 상품, SEO, 주문, 정산, 재고, 알림, 스케줄러, 설정을 그대로 사용합니다.</div></div>', unsafe_allow_html=True)
    st.page_link("pages/00_AutoSeller_Main.py", label="통합 운영 화면 열기", icon="➡️", use_container_width=True)

with right:
    st.markdown('<div class="area"><h3>🛒 소셜커머스 → Threads</h3><div class="muted">Dashboard · 콘텐츠 · 게시물 · 댓글 · HOT Leads · AI Sales Inbox · 자동화 · API 설정을 관리합니다.</div></div>', unsafe_allow_html=True)
    st.page_link("pages/10_Social_Commerce_Threads.py", label="Threads Control Center", icon="🧵", use_container_width=True)
    st.page_link("pages/11_Threads_Growth_Automation.py", label="AI 콘텐츠·예약·Tracking·Attribution", icon="📈", use_container_width=True)

st.markdown("### 🚦 Threads 자동화 단계")
steps = st.columns(5)
for col, title, desc in zip(
    steps,
    ["1. API 연결", "2. AI 콘텐츠", "3. 예약·미디어", "4. AI 영업", "5. 구매 귀속"],
    ["Meta OAuth / 60일 토큰", "상품 DB 기반 생성", "텍스트·이미지·영상", "댓글 분류·답글", "SmartStore·Coupang"],
):
    with col:
        st.markdown(f"**{title}**")
        st.caption(desc)
