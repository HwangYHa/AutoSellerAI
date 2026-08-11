"""기존 통합 운영 화면을 한글 표시 계층과 함께 실행한다."""
from __future__ import annotations

import os
import runpy
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from gui.korean_runtime import apply_korean_patch

apply_korean_patch()

runpy.run_path(
    os.path.join(os.path.dirname(__file__), "..", "legacy_app.py"),
    run_name="__main__",
)
