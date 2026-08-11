"""오토셀러 AI 애플리케이션 허브.

기존 통합 운영 화면과 소셜커머스 기능을 한글 메뉴로 연결한다.
"""
from __future__ import annotations

import streamlit as st

from gui.korean_runtime import apply_korean_patch

apply_korean_patch()

st.set_page_config(
    page_title="오토셀러 AI",
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
      <h1>⚡ 오토셀러 AI</h1>
      <p>상품 수집·등록·주문 운영과 AI 소셜커머스를 하나의 판매 운영 시스템에서 관리합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("## 오토셀러 AI")
st.sidebar.caption("통합 판매 운영 메뉴")
st.sidebar.markdown("### 🧭 운영")
st.sidebar.page_link("pages/00_AutoSeller_Main.py", label="통합 운영 화면", icon="⚡")
st.sidebar.markdown("### 🛒 소셜커머스")
st.sidebar.page_link("pages/10_Social_Commerce_Threads.py", label="스레드 운영센터", icon="🧵")
st.sidebar.page_link("pages/11_Threads_Growth_Automation.py", label="성장 자동화", icon="📈")
st.sidebar.page_link("pages/12_Threads_Profit_Intelligence.py", label="수익 인텔리전스", icon="💹")
st.sidebar.markdown("### 📘 도움말")
st.sidebar.page_link("pages/90_사용자_매뉴얼.py", label="사용자 매뉴얼", icon="📘")
st.sidebar.markdown("---")
st.sidebar.caption("스레드: 콘텐츠 → 게시 → 댓글 영업 → 클릭 → 구매 귀속 → 순이익 학습")

left, right = st.columns(2, gap="large")
with left:
    st.markdown('<div class="area"><h3>⚡ 통합 운영</h3><div class="muted">오토셀러AI의 대시보드, 파이프라인, 상품, 검색 최적화, 주문, 정산, 재고, 알림, 스케줄러, 설정을 사용합니다.</div></div>', unsafe_allow_html=True)
    st.page_link("pages/00_AutoSeller_Main.py", label="통합 운영 화면 열기", icon="➡️", use_container_width=True)

with right:
    st.markdown('<div class="area"><h3>🛒 소셜커머스 → 스레드</h3><div class="muted">현황판 · 콘텐츠 · 게시물 · 댓글 · 구매 가능 고객 · AI 답글함 · 자동화 · 연동 설정과 순이익 기반 학습을 관리합니다.</div></div>', unsafe_allow_html=True)
    st.page_link("pages/10_Social_Commerce_Threads.py", label="스레드 운영센터", icon="🧵", use_container_width=True)
    st.page_link("pages/11_Threads_Growth_Automation.py", label="AI 콘텐츠·예약·추적·구매 귀속", icon="📈", use_container_width=True)
    st.page_link("pages/12_Threads_Profit_Intelligence.py", label="게시물·캠페인 순이익 / 콘텐츠 점수", icon="💹", use_container_width=True)
    st.page_link("pages/90_사용자_매뉴얼.py", label="전체 사용자 매뉴얼", icon="📘", use_container_width=True)

st.markdown("### 🚦 스레드 자동화 단계")
steps = st.columns(6)
for col, title, desc in zip(
    steps,
    ["1. 계정 연동", "2. AI 콘텐츠", "3. 예약·미디어", "4. AI 영업", "5. 구매 귀속", "6. 순이익 학습"],
    ["메타 계정 인증 / 60일 토큰", "상품 데이터 기반 생성", "텍스트·이미지·영상", "댓글 분류·답글", "스마트스토어·쿠팡", "콘텐츠 점수 → 다음 전략"],
):
    with col:
        st.markdown(f"**{title}**")
        st.caption(desc)
