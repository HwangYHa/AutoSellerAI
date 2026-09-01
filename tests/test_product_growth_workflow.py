from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.db import Product, get_db, init_db
from app.image_studio.models import AIImageGeneration, ensure_image_studio_schema
from app.image_studio.schemas import HumanImageRequest
from app.orchestration import product_growth
from app.orchestration.product_growth_models import ensure_product_growth_schema
from app.os.api import app


client = TestClient(app)


def _product(**overrides) -> int:
    init_db()
    token = uuid.uuid4().hex[:10]
    values = {
        "sku": f"growth-{token}",
        "source": "onchannel",
        "source_id": token,
        "source_url": "https://supplier.example/product",
        "name": f"테스트 상품 {token}",
        "supply_price": 5000.0,
        "sell_price": 12900.0,
        "category": "생활용품",
        "brand": "테스트브랜드",
        "origin": "대한민국",
        "material": "ABS",
        "images": json.dumps(["https://cdn.example/product-main.png"]),
        "detail_images": "[]",
        "options": "[]",
        "detail_html": "",
        "status": "ready",
    }
    values.update(overrides)
    with get_db() as db:
        row = Product(**values)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def _workflow(product_id: int, **overrides):
    values = {
        "campaign_key": f"campaign-{uuid.uuid4().hex[:8]}",
        "target_platform": "smartstore",
        "destination_url": "",
        "cta_keyword": "테스트포인트",
        "threads_angle": "problem_solution",
        "threads_tone": "clean",
    }
    values.update(overrides)
    return product_growth.create_workflow(product_id, **values)


def test_product_growth_routes_are_mounted_under_seller_control_plane():
    paths = {getattr(route, "path", "") for route in app.routes}
    expected = {
        "/api/v3/product-growth/catalog",
        "/api/v3/product-growth/workflows",
        "/api/v3/product-growth/workflows/{workflow_id}",
        "/api/v3/product-growth/workflows/{workflow_id}/tracking",
        "/api/v3/product-growth/workflows/{workflow_id}/threads-drafts",
        "/api/v3/product-growth/workflows/{workflow_id}/detail-assets",
        "/api/v3/product-growth/workflows/{workflow_id}/detail-generation",
        "/api/v3/product-growth/workflows/{workflow_id}/social-visual/attach",
        "/api/v3/product-growth/workflows/{workflow_id}/social-visual/stage",
        "/api/v3/product-growth/workflows/{workflow_id}/schedules",
    }
    assert expected.issubset(paths)


def test_campaign_key_is_idempotent_per_product():
    product_id = _product()
    key = f"fixed-{uuid.uuid4().hex[:8]}"
    first = _workflow(product_id, campaign_key=key)
    second = _workflow(product_id, campaign_key=key)
    assert first.id == second.id
    assert first.campaign_key == key


def test_threads_drafts_keep_workflow_product_campaign_context(monkeypatch):
    product_id = _product()
    workflow = _workflow(product_id)
    monkeypatch.setattr(
        product_growth,
        "generate_threads_content",
        lambda *args, **kwargs: [
            {"body": "첫 번째 테스트 본문", "cta_keyword": "테스트포인트", "source": "test", "score": 91.0},
            {"body": "두 번째 테스트 본문", "cta_keyword": "테스트포인트", "source": "test", "score": 87.0},
        ],
    )
    drafts = product_growth.prepare_threads_drafts(workflow.id, count=2)
    assert len(drafts) == 2
    assert all(row.product_id == product_id for row in drafts)
    assert all(row.target_platform == "smartstore" for row in drafts)

    state = product_growth.workflow_to_dict(product_growth.get_workflow(workflow.id))
    assert state["status"] == "content_ready"
    assert {x["id"] for x in state["drafts"]} == {x.id for x in drafts}


def test_detail_assets_update_product_detail_html():
    product_id = _product()
    workflow = _workflow(product_id)
    result = product_growth.register_detail_assets(
        workflow.id,
        ["https://cdn.example/detail-1.png", "https://cdn.example/detail-2.png"],
        apply=True,
    )
    assert result["detail_html_ready"] is True
    with get_db() as db:
        product = db.get(Product, product_id)
        assert "detail-1.png" in product.detail_html
        assert json.loads(product.detail_images) == [
            "https://cdn.example/detail-1.png",
            "https://cdn.example/detail-2.png",
        ]


def test_only_completed_stable_diffusion_generation_can_attach():
    product_id = _product()
    workflow = _workflow(product_id)
    ensure_image_studio_schema()
    req = HumanImageRequest()
    with get_db() as db:
        running = AIImageGeneration(
            status="running",
            request_json=req.model_dump_json(),
            image_paths_json=json.dumps(["/tmp/image.png"]),
        )
        db.add(running)
        db.commit()
        db.refresh(running)
        running_id = running.id

    try:
        product_growth.attach_image_generation(workflow.id, running_id)
    except ValueError:
        pass
    else:
        raise AssertionError("running generation must not be attached")


def test_product_image_can_become_threads_visual():
    product_id = _product()
    workflow = _workflow(product_id)
    result = product_growth.use_product_social_visual(workflow.id, 0)
    assert result["source"] == "product"
    assert result["media_url"] == "https://cdn.example/product-main.png"
    refreshed = product_growth.get_workflow(workflow.id)
    assert refreshed.social_media_url == result["media_url"]


def test_schedule_preserves_campaign_and_does_not_publish_immediately(monkeypatch):
    product_id = _product()
    workflow = _workflow(product_id)
    monkeypatch.setattr(
        product_growth,
        "generate_threads_content",
        lambda *args, **kwargs: [
            {"body": "예약 게시 테스트", "cta_keyword": "테스트포인트", "source": "test", "score": 90.0},
        ],
    )
    draft = product_growth.prepare_threads_drafts(workflow.id, count=1)[0]
    scheduled = product_growth.schedule_workflow_post(
        workflow.id,
        draft_id=draft.id,
        scheduled_at=datetime.utcnow() + timedelta(hours=1),
        media_source="none",
        include_tracking_url=False,
    )
    assert scheduled.status == "scheduled"
    assert scheduled.campaign_key == workflow.campaign_key
    assert scheduled.product_id == product_id
    assert scheduled.media_type == "TEXT"

    state = product_growth.workflow_to_dict(product_growth.get_workflow(workflow.id))
    assert state["status"] == "scheduled"
    assert state["performance"]["published_posts"] == 0


def test_catalog_documents_identity_and_publish_boundaries(monkeypatch):
    monkeypatch.setattr("app.orchestration.product_growth_api.media_base_is_public", lambda: False)
    response = client.get("/api/v3/product-growth/catalog")
    assert response.status_code == 200
    rules = response.json()["design_rules"]
    assert "reference-grounded" in rules["detail_page"]
    assert "not authoritative product identity" in rules["stable_diffusion"]
    assert "schedule" in rules["publishing"]
