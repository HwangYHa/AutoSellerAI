from __future__ import annotations

import ast
from pathlib import Path


def test_product_growth_workspace_is_syntactically_valid_and_linked():
    root = Path(__file__).resolve().parents[1]
    page = (root / "gui/pages/14_상품_성장_워크플로우.py").read_text(encoding="utf-8")
    main = (root / "gui/main.py").read_text(encoding="utf-8")
    oneclick = (root / "app/orchestration/oneclick.py").read_text(encoding="utf-8")

    ast.parse(page)
    assert "상품 상세페이지 · Threads 통합 워크플로우" in page
    assert "queue_detail_generation" in page
    assert "prepare_threads_drafts" in page
    assert "stage_attached_social_visual" in page
    assert "schedule_workflow_post" in page
    assert "Stable Diffusion txt2img는 정확한 상품 복제용이 아닙니다" in page
    assert "pages/14_상품_성장_워크플로우.py" in main
    assert "pages/14_상품_성장_워크플로우.py" in oneclick
