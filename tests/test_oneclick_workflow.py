from app.orchestration import oneclick


def test_workflow_is_strictly_ordered_end_to_end():
    stages = oneclick.WORKFLOW_STAGES
    assert [s.order for s in stages] == list(range(1, 16))
    assert [s.key for s in stages] == [
        "connections", "market_sync", "collect", "select", "images",
        "ai_detail", "seo", "pricing", "listing", "orders",
        "fulfillment", "invoice", "settlement", "threads", "learning",
    ]


def test_irreversible_or_paid_steps_are_not_safe_auto():
    by_key = {s.key: s for s in oneclick.WORKFLOW_STAGES}
    assert by_key["listing"].approval_required is True
    assert by_key["listing"].safe_auto is False
    assert by_key["fulfillment"].approval_required is True
    assert by_key["fulfillment"].safe_auto is False
    assert by_key["ai_detail"].optional is True
    assert by_key["ai_detail"].safe_auto is False


def test_safe_oneclick_runs_only_read_sync_and_image_refresh(monkeypatch):
    calls = []

    def fake_sync():
        calls.append("market_sync")
        return {
            "smartstore": {"ok": True, "total_found": 0},
            "coupang": {"ok": True, "total_found": 0},
        }

    def fake_images(limit=100):
        calls.append("images")
        return {"checked": 0, "updated": 0, "errors": []}

    fake_status = {
        "progress": 0.0,
        "completed_required": 0,
        "required_total": 12,
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
    assert result["ok"] is True
    assert calls == ["market_sync", "images"]
    assert result["next_stage"]["key"] == "connections"


def test_next_stage_skips_optional_until_required_are_done():
    status = {
        "stages": [
            {"key": "ai_detail", "optional": True, "done": False},
            {"key": "listing", "optional": False, "done": False},
        ]
    }
    assert oneclick.get_next_stage(status)["key"] == "listing"
