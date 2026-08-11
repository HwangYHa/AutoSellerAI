"""한글 표시 변환 시 링크·경로·환경변수 같은 기능 식별자를 보호한다."""
from __future__ import annotations

import re
from typing import Any


def install_safe_translate() -> None:
    from gui import korean_runtime

    if getattr(korean_runtime, "_safe_translate_installed", False):
        return

    original = korean_runtime.translate_text
    protect = re.compile(
        r"https?://[^\s<>'\"]+"
        r"|\b[A-Z][A-Z0-9_]{2,}\b"
        r"|(?:[A-Za-z]:\\|/)[^\s<>'\"]+"
    )

    def safe_translate(value: Any) -> Any:
        if not isinstance(value, str) or not value:
            return value

        held: list[str] = []

        def hold(match: re.Match[str]) -> str:
            held.append(match.group(0))
            return f"@@보호{len(held)-1}@@"

        text = protect.sub(hold, value)
        text = original(text)
        for idx, raw in enumerate(held):
            text = text.replace(f"@@보호{idx}@@", raw)
        return text

    korean_runtime.translate_text = safe_translate
    korean_runtime._safe_translate_installed = True
