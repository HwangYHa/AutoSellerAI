from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db import Product, get_db, init_db
from app.orchestration import campaign_director
from app.orchestration.campaign_director_models import ensure_campaign_director_schema
from app.orchestration.product_growth import create_workflow, prepare_threads_drafts
from app.os.api import app
from app.social.threads.models import ThreadsPost


client = TestClient(app)


def _product(*, detail: bool = False) -> int:
    init_db()
    token = uuid.uuid4().hex[:10]
    with get_db() as db:
        row = Product(
            sku=f"director-{token}", source="onchannel", source_id=token,
            source_url="https://supplier.example/item", name=f"Director 테스트 상품 {token}",
            supply_price=5000.0, sell_price=12900.0, category="생활용품",
            brand="테스트", origin="대한민국", material="ABS",
            images=json.dumps(["https://cdn.example/main.png"]),
            detail_images=json.dumps(["https://cdn.example/detail.png"] if detail else []),
            options="[]",
            detail_html='<img src="https://cdn.example/detail.png">' if detail else "",
            status="ready",
        )
        db.add(row); db.commit(); db.refresh(row)
        return row.id


def _workflow(*, detail: bool = False, destination_url: str = ""):
    product_id = _product(detail=detail)
    return create_workflow(
        product_id,
        campaign_key=f"director-{uuid.uuid4().hex[:8]}",
        target_platform="smartstore",
        destination_url=destination_url,
        cta_keyword="포인트",
        threads_angle="problem_solution",
        threads_tone="clean",
    )


def test_campaign_director_routes_are_mounted():
    paths = {getattr(route, "path", "") for route in app.routes}
    expected = {
        "/api/v3/product-growth/workflows/{workflow_id}/director",
        "/api/v3/product-growth/workflows/{workflow_id}/director/plan",
        "/api/v3/product-growth/workflows/{workflow_id}/director/prepare",
        "/api/v3/product-growth/workflows/{workflow_id}/director/schedule",
    }
    assert expected.issubset(paths)


def test_plan_is_local_persisted_and_idempotent():
    workflow = _workflow(detail=True)
    ensure_campaign_director_schema()
    first = campaign_director.build_campaign_plan(workflow.id)
    second = campaign_director.build_campaign_plan(workflow.id)
    assert first["id"] == second["id"]
    assert first["fingerprint"] == second["fingerprint"]
    assert second["reused"] is True
    plan = second["plan"]
    assert plan["quality_gates"]["publishing"].startswith("Campaign Director prepare")
    assert plan["recommended"]["social_visual"]["source"] == "detail"


def test_default_prepare_never_calls_ai_copy_or_paid_detail(monkeypatch):
    workflow = _workflow(detail=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("cost-bearing function must not run without explicit permission")

    monkeypatch.setattr(campaign_director, "prepare_threads_drafts", forbidden)
    monkeypatch.setattr(campaign_director, "queue_detail_generation", forbidden)
    result = campaign_director.prepare_campaign(
        workflow.id,
        allow_ai_content=False,
        allow_paid_detail_generation=False,
    )
    assert result["ok"] is True
    by_step = {x["step"]: x for x in result["results"]}
    assert by_step["threads_copy"]["skipped"] is True
    assert by_step["detail_generation"]["skipped"] is True
    assert by_step["social_visual"]["source"] == "product"


def test_ai_copy_runs_only_when_explicitly_allowed(monkeypatch):
    workflow = _workflow(detail=True)
    calls = []

    def fake_drafts(workflow_id, *, count, force):
        calls.append((workflow_id, count, force))
        return [SimpleNamespace(id=11), SimpleNamespace(id=12)]

    monkeypatch.setattr(campaign_director, "prepare_threads_drafts", fake_drafts)
    result = campaign_director.prepare_campaign(workflow.id, allow_ai_content=True, draft_count=2)
    assert calls == [(workflow.id, 2, False)]
    step = next(x for x in result["results"] if x["step"] == "threads_copy")
    assert step["draft_ids"] == [11, 12]


def test_paid_detail_generation_runs_only_when_explicitly_allowed(monkeypatch):
    workflow = _workflow(detail=False)
    calls = []

    def fake_queue(workflow_id, *, count, apply):
        calls.append((workflow_id, count, apply))
        return {"accepted": True, "job_id": "detail-job-1", "queue": "image", "reused": False}

    monkeypatch.setattr(campaign_director, "queue_detail_generation", fake_queue)
    result = campaign_director.prepare_campaign(workflow.id, allow_paid_detail_generation=True)
    assert calls == [(workflow.id, 3, True)]
    step = next(x for x in result["results"] if x["step"] == "detail_generation")
    assert step["job_id"] == "detail-job-1"


def test_director_schedule_is_explicit_future_action_not_immediate_publish():
    workflow = _workflow(detail=True)
    drafts = prepare_threads_drafts(workflow.id, count=1)
    assert drafts
    before = 0
    with get_db() as db:
        before = db.query(ThreadsPost).count()

    result = campaign_director.schedule_director_post(
        workflow.id,
        draft_id=drafts[0].id,
        scheduled_at=datetime.utcnow() + timedelta(hours=1),
        media_source="detail",
        include_tracking_url=False,
    )
    assert result["ok"] is True
    assert result["schedule_id"] > 0
    with get_db() as db:
        assert db.query(ThreadsPost).count() == before


def test_director_schedule_refuses_when_no_drafts():
    workflow = _workflow(detail=True)
    try:
        campaign_director.schedule_director_post(
            workflow.id,
            scheduled_at=datetime.utcnow() + timedelta(hours=1),
            include_tracking_url=False,
        )
    except ValueError as exc:
        assert "drafts are not prepared" in str(exc)
    else:
        raise AssertionError("director must not silently generate copy while scheduling")


def test_director_plan_api_returns_cost_tiers():
    workflow = _workflow(detail=False)
    response = client.post(
        f"/api/v3/product-growth/workflows/{workflow.id}/director/plan",
        json={"force": False},
    )
    assert response.status_code == 201
    tiers = {x["tier"] for x in response.json()["plan"]["actions"]}
    assert {"local", "ai_compute", "ai_cost", "external_publish"}.issubset(tiers)
