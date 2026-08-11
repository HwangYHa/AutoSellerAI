"""한글 표시 패치에서 빠지기 쉬운 Streamlit 컨트롤 보강."""
from __future__ import annotations

from functools import wraps


def apply_extra_korean_patch() -> None:
    try:
        import streamlit as st
        from streamlit.delta_generator import DeltaGenerator
        from gui.korean_runtime import translate_text
    except Exception:
        return

    if getattr(st, "_autoseller_extra_korean_patch", False):
        return

    for name in ("form_submit_button", "chat_input"):
        if not hasattr(DeltaGenerator, name):
            continue
        original = getattr(DeltaGenerator, name)

        @wraps(original)
        def wrapped(self, label, *args, __original=original, **kwargs):
            return __original(self, translate_text(label), *args, **kwargs)

        setattr(DeltaGenerator, name, wrapped)

    if hasattr(DeltaGenerator, "progress"):
        original_progress = DeltaGenerator.progress

        @wraps(original_progress)
        def progress(self, value, text=None, *args, **kwargs):
            return original_progress(self, value, text=translate_text(text), *args, **kwargs)

        DeltaGenerator.progress = progress

    st._autoseller_extra_korean_patch = True
