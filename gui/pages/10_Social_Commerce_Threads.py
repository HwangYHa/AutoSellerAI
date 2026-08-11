"""AutoSellerAI — Social Commerce → Threads unified control center."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st

from gui.threads_workspace import render

st.set_page_config(
    page_title="Social Commerce → Threads | AutoSeller AI",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.markdown("## 🛒 소셜커머스")
st.sidebar.page_link("app.py", label="Seller OS 홈", icon="🏠")
st.sidebar.page_link("pages/10_Social_Commerce_Threads.py", label="Threads", icon="🧵")
st.sidebar.page_link("pages/11_Threads_Growth_Automation.py", label="Growth Automation", icon="📈")

render()
