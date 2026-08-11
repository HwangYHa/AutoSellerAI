"""Streamlit 페이지 설정의 사용자 노출 제목을 한글화한다."""
from __future__ import annotations

from functools import wraps


def patch_page_config() -> None:
    try:
        import streamlit as st
        from gui.korean_runtime import translate_text
    except Exception:
        return

    if getattr(st, "_autoseller_pageconfig_ko", False):
        return

    original = st.set_page_config

    @wraps(original)
    def wrapped(*args, **kwargs):
        if "page_title" in kwargs and kwargs["page_title"]:
            kwargs["page_title"] = translate_text(kwargs["page_title"])
        return original(*args, **kwargs)

    st.set_page_config = wrapped
    st._autoseller_pageconfig_ko = True
