from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import get_db
from app.image_studio.models import AIImageGeneration, ensure_image_studio_schema
from app.image_studio.schemas import HumanImageRequest
from app.image_studio import api as image_api
from app.image_studio import service as image_service
from app.os.api import app


client = TestClient(app)


def _insert_generation(**overrides) -> int:
    ensure_image_studio_schema()
    req = HumanImageRequest()
    values = {
        "status": "completed",
        "preset": req.preset,
        "subject_summary": "test",
        "request_json": req.model_dump_json(),
        "prompt": "p",
        "negative_prompt": "n",
        "response_info_json": json.dumps({"all_seeds": [123456]}),
        "image_paths_json": "[]",
    }
    values.update(overrides)
    with get_db() as db:
        row = AIImageGeneration(**values)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def test_image_studio_routes_are_mounted_under_control_plane():
    paths = {getattr(route, "path", "") for route in app.routes}
    expected = {
        "/api/v3/image-studio/health",
        "/api/v3/image-studio/catalog",
        "/api/v3/image-studio/preview",
        "/api/v3/image-studio/generations",
        "/api/v3/image-studio/generations/{generation_id}",
        "/api/v3/image-studio/generations/{generation_id}/retry",
        "/api/v3/image-studio/generations/{generation_id}/cancel",
        "/api/v3/image-studio/generations/{generation_id}/images/{image_index}",
        "/api/v3/image-studio/progress",
    }
    assert expected.issubset(paths)


def test_preview_works_when_webui_is_offline(monkeypatch):
    monkeypatch.setattr(
        image_api,
        "_capabilities",
        lambda: {"ok": False, "error": "offline", "upscalers": [], "adetailer_available": False},
    )
    response = client.post("/api/v3/image-studio/preview", json=HumanImageRequest().model_dump())
    assert response.status_code == 200
    body = response.json()
    assert "adult Korean woman" in body["positive_prompt"]
    assert body["webui_online"] is False
    assert body["payload"]["prompt"] == body["positive_prompt"]
    assert body["warnings"]


def test_generate_is_rejected_when_runtime_not_ready(monkeypatch):
    monkeypatch.setattr(image_api, "_capabilities", lambda: {"ok": False, "error": "webui offline"})
    monkeypatch.setattr(
        image_api,
        "get_image_queue_status",
        lambda: {"ok": True, "workers": 1, "queued": 0, "worker_rows": [], "error": ""},
    )
    response = client.post("/api/v3/image-studio/generations", json=HumanImageRequest().model_dump())
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "problems" in detail
    assert any("offline" in x for x in detail["problems"])


def test_catalog_exposes_only_adult_age_choices(monkeypatch):
    monkeypatch.setattr(image_api, "_capabilities", lambda: {"ok": False, "error": "offline"})
    response = client.get("/api/v3/image-studio/catalog")
    assert response.status_code == 200
    ages = response.json()["options"]["age"]
    assert ages
    assert all("10대" not in item for item in ages)
    assert "20대 초반" in ages


def test_retry_same_seed_restores_actual_generation_seed(monkeypatch):
    row_id = _insert_generation()
    captured = {}

    def fake_create(req):
        captured["request"] = req
        return req

    monkeypatch.setattr(image_service, "create_generation", fake_create)
    result = image_service.retry_generation(row_id, same_seed=True)
    assert result.seed == 123456
    assert captured["request"].seed == 123456


def test_retry_random_seed_forces_minus_one(monkeypatch):
    req = HumanImageRequest(seed=999)
    row_id = _insert_generation(request_json=req.model_dump_json())
    monkeypatch.setattr(image_service, "create_generation", lambda request: request)
    result = image_service.retry_generation(row_id, same_seed=False)
    assert result.seed == -1


def test_generation_image_must_stay_inside_configured_root(tmp_path, monkeypatch):
    root = tmp_path / "generated"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"not an image")
    monkeypatch.setenv("SD_IMAGE_OUTPUT_DIR", str(root))
    row_id = _insert_generation(image_paths_json=json.dumps([str(outside)]))

    try:
        image_service.resolve_generation_image(row_id, 0)
    except PermissionError:
        pass
    else:
        raise AssertionError("outside image path should be rejected")


def test_generation_response_hides_internal_file_paths():
    row_id = _insert_generation(image_paths_json=json.dumps(["/secret/internal/a.png"]))
    row = image_service.get_generation(row_id)
    body = image_api._generation_response(row)
    assert "image_paths" not in body
    assert body["image_count"] == 1
    assert body["images"][0]["url"].endswith(f"/{row_id}/images/0")
    assert "/secret/internal" not in json.dumps(body)
