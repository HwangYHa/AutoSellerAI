from __future__ import annotations

import ast
from pathlib import Path


def test_user_manual_is_valid_and_covers_latest_operating_surfaces():
    root = Path(__file__).resolve().parents[1]
    manual_path = root / "gui/manual_content.py"
    main_path = root / "gui/main.py"

    manual = manual_path.read_text(encoding="utf-8")
    main = main_path.read_text(encoding="utf-8")

    ast.parse(manual)

    assert 'SELLER_OS_VERSION = "3.3"' in manual
    assert 'UPDATED_AT = "2026-09-01"' in manual
    assert '"main.py"' in manual
    assert '"app.py"' not in manual

    for label in [
        "Seller OS",
        "주문·발주 관제센터",
        "통합 판매 운영센터",
        "커머스 자동화 제어센터",
        "통합 상품 소싱",
        "콘텐츠 스튜디오",
        "AI 인물 이미지 스튜디오",
        "AI 체형 프리셋",
        "상품 성장 워크플로우",
        "AI Campaign Director",
        "마케팅 · Threads",
    ]:
        assert label in manual
        assert label in main

    for safety_contract in [
        "allow_ai_content=true",
        "allow_paid_detail_generation=true",
        "external_publish",
        "Prepare",
        "Card",
    ]:
        if safety_contract == "Card":
            assert "카드사 앱 본인승인" in manual
        else:
            assert safety_contract in manual

    for runtime_contract in [
        "--api --listen --port 7860",
        "host.docker.internal:7860",
        "image-worker",
        "PUBLIC_BASE_URL",
        "SELLER_API_TOKEN",
    ]:
        assert runtime_contract in manual

    for profile in ["매우 슬림", "슬림", "슬림 글래머", "균형형", "볼륨형", "운동형"]:
        assert profile in manual


def test_manual_documents_latest_rest_routes():
    root = Path(__file__).resolve().parents[1]
    manual = (root / "gui/manual_content.py").read_text(encoding="utf-8")

    routes = [
        "/api/v3/image-studio/health",
        "/api/v3/image-studio/catalog",
        "/api/v3/image-studio/body-profiles",
        "/api/v3/image-studio/preview",
        "/api/v3/image-studio/generations",
        "/api/v3/product-growth/workflows/{id}/director",
        "/api/v3/product-growth/workflows/{id}/director/plan",
        "/api/v3/product-growth/workflows/{id}/director/prepare",
        "/api/v3/product-growth/workflows/{id}/director/schedule",
    ]
    for route in routes:
        assert route in manual
