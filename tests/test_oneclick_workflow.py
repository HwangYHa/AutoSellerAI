from app.orchestration import oneclick


def test_workflow_is_strictly_ordered_end_to_end():
    stages = oneclick.WORKFLOW_STAGES
    assert [s.order for s in stages] == list(range(1, 9))
    assert [s.key for s in stages] == [
        "connections", "acquire", "prepare", "listing",
        "orders", "fulfillment", "settlement", "growth",
    ]


def test_irreversible_steps_are_not_safe_auto():
    by_key = {s.key: s for s in oneclick.WORKFLOW_STAGES}
    assert by_key["listing"].approval_required is True
    assert by_key["listing"].safe_auto is False
    assert by_key["fulfillment"].approval_required is True
    assert by_key["fulfillment"].safe_auto is False
    assert by_key["growth"].optional is True


def test_naver_commerce_secret_validation():
    assert oneclick._valid_naver_commerce_secret("$2a$04$1234567890123456789012") is True
    assert oneclick._valid_naver_commerce_secret("$$2a$$04$$1234567890123456789012") is True
    assert oneclick._valid_naver_commerce_secret("normal-secret") is False


def test_safe_oneclick_runs_read_sync_and_image_refresh(monkeypatch):
    calls = []

    def fake_sync():
        calls.append("market_sync")
        return {
            "smartstore": {"ok": False, "error": "not configured"},
            "coupang": {"ok": True, "total_found": 0},
        }

    def fake_images(limit=100):
        calls.append("images")
        return {"checked": 0, "updated": 0, "errors": []}

    fake_status = {
        "progress": 0.0,
        "completed_required": 0,
        "required_total": 7,
        "connections": {},
        "counts": {},
        "stages": [
            {"order": 1, "key": "connections", "optional": False, "done": False}
        ],
    }

    monkeypatch.setattr(oneclick, "_sync_marketplace_catalogs", fake_sync)
    monkeypatch.setattr(oneclick, "_refresh_supplier_images", fake_images)
    monkeypatch.setattr(oneclick, "get_process_status", lambda: fake_status)

    result = oneclick.run_safe_oneclick()
    # 한 채널이 성공하면 성공한 동기화 결과를 유지한다.
    assert result["ok"] is True
    assert calls == ["market_sync", "images"]
    assert result["next_stage"]["key"] == "connections"


def test_next_stage_skips_optional_until_required_are_done():
    status = {
        "stages": [
            {"key": "growth", "optional": True, "done": False},
            {"key": "listing", "optional": False, "done": False},
        ]
    }
    assert oneclick.get_next_stage(status)["key"] == "listing"
