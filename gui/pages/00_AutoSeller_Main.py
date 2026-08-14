"""Seller OS v3 entry page.

Business logic lives under app.os; this page is intentionally a thin UI shell.
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from gui.korean_runtime import apply_korean_patch
from gui.seller_os_v3 import render_seller_os_v3

apply_korean_patch()

st.set_page_config(
    page_title="Seller OS | AutoSellerAI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_seller_os_v3()
