"""AutoSellerAI — 소셜커머스 → 스레드 통합 운영센터."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st

from gui.threads_workspace import render

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

render()
