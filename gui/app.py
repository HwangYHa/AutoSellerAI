"""AutoSellerAI — Seller OS v3 is the default operating surface."""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from gui.help_center import render_sidebar_help
from gui.korean_runtime import apply_korean_patch
from gui.seller_os_v3 import render_seller_os_v3

apply_korean_patch()

st.set_page_config(
    page_title="AutoSellerAI · Seller OS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# One operating OS. Auxiliary workspaces are opened only when their specific work
# is needed; supplier/channel-specific setup pages are no longer normal navigation.
st.sidebar.markdown("## ⚡ AutoSellerAI")
st.sidebar.caption("Seller OS · 하나의 운영 흐름")
st.sidebar.page_link("app.py", label="Seller OS", icon="🎯")
st.sidebar.page_link("pages/05_Order_Fulfillment_Monitor.py", label="주문·발주 관제센터", icon="🛰️")

st.sidebar.markdown("### 보조 작업공간")
st.sidebar.page_link("pages/30_상품소싱.py", label="통합 상품 소싱", icon="🔎")
st.sidebar.page_link("pages/25_AI_상세페이지_제작.py", label="콘텐츠 스튜디오", icon="🖼️")
st.sidebar.page_link("pages/10_Social_Commerce_Threads.py", label="마케팅 · Threads", icon="🧵")

st.sidebar.markdown("---")
render_sidebar_help()
st.sidebar.page_link("pages/90_사용자_매뉴얼.py", label="사용자 매뉴얼", icon="📘")

render_seller_os_v3()