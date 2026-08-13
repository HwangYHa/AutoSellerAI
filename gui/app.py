"""오토셀러 AI 허브 — 업무 목적 중심의 최소 내비게이션."""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from app.orchestration.oneclick import get_next_stage, get_process_status
from app.policies.runtime_patch import apply_fulfillment_policy_patch
from gui.help_center import render_sidebar_help
from gui.korean_runtime import apply_korean_patch

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
    .block-container{max-width:1180px;padding-top:1.6rem}
    .hub-hero{background:linear-gradient(135deg,#0f172a,#312e81);color:#fff;
      border-radius:18px;padding:26px 30px;margin-bottom:18px}
    .hub-hero h1{margin:0;font-size:29px;font-weight:850}.hub-hero p{margin:8px 0 0;color:#cbd5e1}
    [data-testid="stMetric"]{border:1px solid #e2e8f0;border-radius:12px;padding:12px;background:white}
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# 사이드바: 같은 기능을 두 번 노출하지 않는다.
# -----------------------------------------------------------------------------
st.sidebar.markdown("## ⚡ 오토셀러 AI")
st.sidebar.caption("업무 목적대로 한 번만 노출")

st.sidebar.markdown("### 운영")
st.sidebar.page_link("pages/00_AutoSeller_Main.py", label="Seller OS", icon="📦")
st.sidebar.page_link("pages/01_원큐_운영.py", label="원큐 자동화", icon="🚀")

st.sidebar.markdown("### 상품 확보")
st.sidebar.page_link("pages/30_상품소싱.py", label="통합 상품 소싱", icon="🔎")
st.sidebar.page_link("pages/25_AI_상세페이지_제작.py", label="이미지 · AI 상세페이지", icon="🖼️")

st.sidebar.markdown("### 연동 설정")
st.sidebar.page_link("pages/05_판매채널_상품동기화.py", label="쿠팡 · 스마트스토어", icon="🔄")
st.sidebar.page_link("pages/20_오너클랜_연동.py", label="오너클랜", icon="🏬")
st.sidebar.page_link("pages/21_도매꾹_연동.py", label="도매꾹", icon="🏷️")
st.sidebar.page_link("pages/22_온채널_연동.py", label="온채널", icon="🛍️")

st.sidebar.markdown("### 마케팅 · 학습")
st.sidebar.page_link("pages/10_Social_Commerce_Threads.py", label="스레드 판매", icon="🧵")
st.sidebar.page_link("pages/12_Threads_Profit_Intelligence.py", label="수익 학습", icon="💹")

st.sidebar.markdown("---")
render_sidebar_help()
st.sidebar.page_link("pages/90_사용자_매뉴얼.py", label="사용자 매뉴얼", icon="📘")

# -----------------------------------------------------------------------------
# 홈: 기능 카탈로그가 아니라 현재 상태 + 다음 행동을 보여준다.
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="hub-hero">
      <h1>⚡ 오토셀러 AI</h1>
      <p>상품 확보 → 판매 준비 → 채널 등록 → 주문/배송 → 실제 수익까지 하나의 운영 흐름으로 관리합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

status = get_process_status()
next_stage = get_next_stage(status)
counts = status.get("counts", {})

m1, m2, m3, m4 = st.columns(4)
m1.metric("전체 상품", counts.get("products", 0))
m2.metric("판매중", counts.get("listed_products", 0))
m3.metric("수집 주문", counts.get("platform_orders", 0))
m4.metric("필수 진행률", f"{int(float(status.get('progress', 0)) * 100)}%")

st.markdown("### 지금 할 일")
with st.container(border=True):
    if next_stage:
        left, right = st.columns([4, 1.2], vertical_alignment="center")
        with left:
            st.markdown(f"#### {next_stage['order']:02d}. {next_stage['title']}")
            st.write(next_stage["description"])
        with right:
            st.page_link(next_stage["page"], label="다음 작업 열기", icon="➡️", use_container_width=True)
    else:
        st.success("필수 프로세스가 모두 완료 상태입니다. Seller OS에서 상품·주문·수익 상태를 확인하세요.")

st.markdown("### 가장 많이 쓰는 3개 화면")
a, b, c = st.columns(3)
with a:
    with st.container(border=True):
        st.markdown("#### 📦 Seller OS")
        st.write("상품·주문·배송·수익을 평소에는 여기서만 관리합니다.")
        st.page_link("pages/00_AutoSeller_Main.py", label="Seller OS 열기", use_container_width=True)
with b:
    with st.container(border=True):
        st.markdown("#### 🔎 통합 상품 소싱")
        st.write("도매꾹·도매매·온채널·오너클랜을 한 번에 검색하고 비교합니다.")
        st.page_link("pages/30_상품소싱.py", label="상품 찾기", use_container_width=True)
with c:
    with st.container(border=True):
        st.markdown("#### 🚀 원큐 자동화")
        st.write("안전한 조회·동기화를 자동 실행하고 다음 단계만 안내받습니다.")
        st.page_link("pages/01_원큐_운영.py", label="원큐 운영", use_container_width=True)

st.markdown("### 운영 규칙")
st.info(
    "평소에는 **Seller OS**만 사용하세요. 새 상품이 필요할 때만 **통합 상품 소싱**, "
    "인증정보가 바뀌거나 동기화 오류가 있을 때만 **연동 설정**을 사용합니다. "
    "공급처별 연동 페이지는 설정/진단용이며 일상 상품관리 메뉴가 아닙니다."
)
