"""AutoSellerAI — 소셜커머스 → 스레드 통합 운영센터."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st

import gui.threads_workspace as threads_workspace
from app.social.threads.marketing_playbook import generate_threads_content_with_playbook

# Apply the marketing playbook to the actual content-generation path used by
# this page. The workspace imported the base function directly, so replacing
# that reference here makes every "AI 콘텐츠 생성" action on this route use
# the playbook without changing unrelated background jobs or APIs.
threads_workspace.generate_threads_content = generate_threads_content_with_playbook

st.set_page_config(
    page_title="소셜커머스 → 스레드 | AutoSeller AI",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.markdown("## 🛒 소셜커머스")
st.sidebar.page_link("main.py", label="통합 판매 홈", icon="🏠")
st.sidebar.page_link("pages/10_Social_Commerce_Threads.py", label="스레드 운영센터", icon="🧵")
st.sidebar.page_link("pages/11_Threads_Growth_Automation.py", label="성장 자동화", icon="📈")
st.sidebar.page_link("pages/12_Threads_Profit_Intelligence.py", label="수익 인텔리전스", icon="💹")
st.sidebar.page_link("pages/90_사용자_매뉴얼.py", label="사용자 매뉴얼", icon="📘")

with st.sidebar.expander("🚀 반응도 공식 적용됨", expanded=False):
    st.caption("AI 콘텐츠 후보를 만든 뒤 아래 기준으로 다시 점수화하고 상위 후보만 노출합니다.")
    st.markdown(
        "- 표본을 넓힌 대중적 주제\n"
        "- 숫자·질문·의외성 첫 문장 후킹\n"
        "- 제품 강점·확인 사실로 가치 입증\n"
        "- 짧은 문장과 잦은 줄바꿈\n"
        "- 사진/영상 활용 준비도\n"
        "- 댓글·대화 유도 가능성"
    )

threads_workspace.render()
