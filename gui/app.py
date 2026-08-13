"""오토셀러 AI 애플리케이션 허브 — 실제 판매 업무 순서 중심 내비게이션."""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from gui.help_center import render_process_overview, render_sidebar_help
from gui.korean_runtime import apply_korean_patch
from app.policies.runtime_patch import apply_fulfillment_policy_patch

apply_korean_patch()
apply_fulfillment_policy_patch()

st.set_page_config(
    page_title="오토셀러 AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {max-width:1180px;padding-top:2rem}
    .hub-hero {background:linear-gradient(135deg,#111827,#312E81 55%,#6D28D9);color:#fff;
      border-radius:20px;padding:28px 32px;margin-bottom:22px;box-shadow:0 16px 44px rgba(49,46,129,.2)}
    .hub-hero h1{margin:0;font-size:30px;font-weight:850}.hub-hero p{margin:8px 0 0;color:rgba(255,255,255,.75)}
    .area{border:1px solid #E2E8F0;border-radius:16px;padding:18px;background:#fff;margin-bottom:14px}
    .muted{color:#64748B;font-size:13px}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hub-hero">
      <h1>⚡ 오토셀러 AI</h1>
      <p>처음 설정부터 상품 수집·등록·주문·발주·배송·정산·광고·수익학습까지 한 흐름으로 운영합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# 사이드바: 실제 업무 순서와 동일하게 고정
# -----------------------------------------------------------------------------
st.sidebar.markdown("## 오토셀러 AI")
st.sidebar.caption("처음부터 끝까지 순서대로 운영")

st.sidebar.markdown("### 🚀 00. 원큐 운영")
st.sidebar.page_link("pages/01_원큐_운영.py", label="전체 프로세스 한큐 진행", icon="🚀")

st.sidebar.markdown("### 🔌 01. 초기 연동")
st.sidebar.page_link("pages/20_오너클랜_연동.py", label="공급처 · 오너클랜 연동", icon="🏬")
st.sidebar.page_link("pages/05_판매채널_상품동기화.py", label="쿠팡 · 스마트스토어 동기화", icon="🔄")

st.sidebar.markdown("### 📦 02~09. 상품 판매 준비")
st.sidebar.page_link("pages/00_AutoSeller_Main.py", label="상품 수집 · 선별 · SEO · 가격 · 등록", icon="⚡")
st.sidebar.page_link("pages/25_AI_상세페이지_제작.py", label="이미지 · AI 상세페이지", icon="🖼️")

st.sidebar.markdown("### 🚚 10~13. 주문 운영")
st.sidebar.page_link("pages/00_AutoSeller_Main.py", label="주문 · 발주 · 송장 · 정산", icon="📦")

st.sidebar.markdown("### 🧵 14. 소셜 판매")
st.sidebar.page_link("pages/10_Social_Commerce_Threads.py", label="스레드 운영센터", icon="🧵")
st.sidebar.page_link("pages/11_Threads_Growth_Automation.py", label="콘텐츠 · 성장 자동화", icon="📈")

st.sidebar.markdown("### 💹 15. 수익 학습")
st.sidebar.page_link("pages/12_Threads_Profit_Intelligence.py", label="수익 인텔리전스", icon="💹")

st.sidebar.markdown("---")
render_sidebar_help()
st.sidebar.markdown("---")
st.sidebar.page_link("pages/90_사용자_매뉴얼.py", label="전체 사용자 매뉴얼", icon="📘")

# -----------------------------------------------------------------------------
# 홈: 원큐 운영을 첫 진입점으로 고정
# -----------------------------------------------------------------------------
st.markdown("### 🚀 가장 빠른 시작")
with st.container(border=True):
    left, right = st.columns([3, 1])
    with left:
        st.markdown("#### 전체 프로세스 한큐 운영")
        st.write("현재 상태를 자동 진단하고, 완료된 단계는 건너뛰며 다음 필요한 단계부터 01→15 순서로 안내합니다. 조회·동기화 작업은 안전하게 한 번에 실행하고 실제 상품등록·공급처 발주는 승인 후 실행합니다.")
    with right:
        st.page_link("pages/01_원큐_운영.py", label="🚀 원큐 운영 시작", use_container_width=True)

st.markdown("### 🧭 전체 프로세스")
process_names = [
    "01 초기 설정/API", "02 기존상품 동기화", "03 공급처 수집", "04 AI 상품 선별",
    "05 이미지 수집", "06 AI 상세페이지", "07 SEO·GEO·AEO", "08 가격·순이익",
    "09 판매채널 등록", "10 주문 수집", "11 공급처 발주", "12 송장·배송",
    "13 정산·순이익", "14 스레드 판매", "15 구매귀속·수익학습",
]
for start in range(0, len(process_names), 5):
    cols = st.columns(5)
    for col, label in zip(cols, process_names[start:start + 5]):
        with col:
            st.markdown(f"**{label}**")

st.markdown("### 🧩 세부 작업 화면")
a, b, c = st.columns(3)
with a:
    with st.container(border=True):
        st.markdown("#### ① 연결 · 상품 확보")
        st.write("판매채널 기존상품과 공급처 상품을 내부 기준으로 모읍니다.")
        st.page_link("pages/20_오너클랜_연동.py", label="오너클랜 연결", icon="🏬", use_container_width=True)
        st.page_link("pages/05_판매채널_상품동기화.py", label="판매상품 동기화", icon="🔄", use_container_width=True)
with b:
    with st.container(border=True):
        st.markdown("#### ② 판매 준비 · 주문 운영")
        st.write("상품 선별 → 이미지 → SEO → 가격 → 등록 → 주문 → 발주 → 배송 → 정산을 처리합니다.")
        st.page_link("pages/25_AI_상세페이지_제작.py", label="이미지 · 상세페이지", icon="🖼️", use_container_width=True)
        st.page_link("pages/00_AutoSeller_Main.py", label="통합 판매 운영", icon="⚡", use_container_width=True)
with c:
    with st.container(border=True):
        st.markdown("#### ③ 광고 · 수익 학습")
        st.write("스레드 콘텐츠와 추적링크를 운영하고 실제 순이익을 다음 콘텐츠 전략에 반영합니다.")
        st.page_link("pages/10_Social_Commerce_Threads.py", label="스레드 운영", icon="🧵", use_container_width=True)
        st.page_link("pages/12_Threads_Profit_Intelligence.py", label="수익 학습", icon="💹", use_container_width=True)

render_process_overview(expanded=False)
