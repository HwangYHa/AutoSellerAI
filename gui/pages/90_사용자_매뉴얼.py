"""오토셀러AI 전체 프로세스 사용자 매뉴얼."""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from gui.korean_runtime import apply_korean_patch
from gui.manual_content import render_manual
from gui.pageconfig_ko import patch_page_config

apply_korean_patch()
patch_page_config()

st.set_page_config(page_title="사용자 매뉴얼 | 오토셀러 AI", page_icon="📘", layout="wide")
render_manual()
