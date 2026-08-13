"""도매꾹 공식 Open API 연동 화면."""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from gui.korean_runtime import apply_korean_patch
from gui.supplier_link_workspace import render_supplier_workspace

apply_korean_patch()
st.set_page_config(page_title="도매꾹 연동 | 오토셀러 AI", page_icon="🏷️", layout="wide")
render_supplier_workspace("domeggook")
