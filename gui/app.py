"""오토셀러 AI 애플리케이션 허브.

기존 통합 운영 화면과 소셜커머스 기능을 한글 메뉴로 연결한다.
"""
from __future__ import annotations

import os
import sys

# `streamlit run gui/app.py`로 직접 실행해도 프로젝트 루트 패키지를 찾도록 보장한다.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from gui.help_center import render_process_overview, render_sidebar_help
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
st.sidebar.page_link("pages/05_판매채널_상품동기화.py", label="판매채널 상품 동기화", icon="🔄")
st.sidebar.markdown("### 🏭 공급처")
st.sidebar.page_link("pages/20_오너클랜_연동.py", label="오너클랜 연동", icon="🏬")
st.sidebar.markdown("### 🛒 소셜커머스")
st.sidebar.page_link("pages/10_Social_Commerce_Threads.py", label="스레드 운영센터", icon="🧵")
st.sidebar.page_link("pages/11_Threads_Growth_Automation.py", label="성장 자동화", icon="📈")
st.sidebar.page_link("pages/12_Threads_Profit_Intelligence.py", label="수익 인텔리전스", icon="💹")
st.sidebar.markdown("---")
render_sidebar_help()
st.sidebar.markdown("---")
st.sidebar.caption("스레드: 콘텐츠 → 게시 → 댓글 영업 → 클릭 → 구매 귀속 → 순이익 학습")

render_process_overview(expanded=True)

st.markdown("### 🚀 어디서 시작하면 되나요?")
start1, start2, start3 = st.columns(3)
with start1:
    with st.container(border=True):
        st.markdown("#### ① 처음 설정")
        st.write("판매채널·공급처·AI·스레드 인증정보를 먼저 준비합니다.")
        st.page_link("pages/20_오너클랜_연동.py", label="오너클랜 판매사 API 연결", icon="🏬", use_container_width=True)
        st.page_link("pages/90_사용자_매뉴얼.py", label="초기 설정 방법", icon="🔐", use_container_width=True)
with start2:
    with st.container(border=True):
        st.markdown("#### ② 상품 판매 운영")
        st.write("판매자센터 직접 등록 상품을 먼저 동기화한 뒤, 상품 수집 → 선별 → 검색 최적화 → 등록 → 주문·배송·정산을 진행합니다.")
        st.page_link("pages/05_판매채널_상품동기화.py", label="판매채널 상품 동기화", icon="🔄", use_container_width=True)
        st.page_link("pages/00_AutoSeller_Main.py", label="통합 운영 시작", icon="⚡", use_container_width=True)
with start3:
    with st.container(border=True):
        st.markdown("#### ③ 소셜 판매 자동화")
        st.write("상품 등록 후 스레드 콘텐츠·댓글 영업·구매 귀속·수익 학습을 연결합니다.")
        st.page_link("pages/10_Social_Commerce_Threads.py", label="스레드 운영 시작", icon="🧵", use_container_width=True)

st.markdown("### 🧩 주요 기능")
left, right = st.columns(2, gap="large")
with left:
    st.markdown('<div class="area"><h3>⚡ 통합 운영</h3><div class="muted">오토셀러AI의 대시보드, 파이프라인, 상품, 검색 최적화, 주문, 정산, 재고, 알림, 스케줄러, 설정을 사용합니다.</div></div>', unsafe_allow_html=True)
    st.page_link("pages/20_오너클랜_연동.py", label="오너클랜 상품·주문 API", icon="🏬", use_container_width=True)
    st.page_link("pages/05_판매채널_상품동기화.py", label="쿠팡·스마트스토어 상품 가져오기", icon="🔄", use_container_width=True)
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
