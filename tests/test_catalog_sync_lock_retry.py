from sqlalchemy.exc import OperationalError

from app.sync import catalog_sync


def _locked_error():
    return OperationalError("UPDATE products SET name=?", {}, Exception("database is locked"))


def test_sync_retries_only_locked_item(monkeypatch):
    calls = {"1": 0, "2": 0}

    def fake_sync_one(platform, item):
        pid = item["platform_id"]
        calls[pid] += 1
        if pid == "1" and calls[pid] == 1:
            raise _locked_error()
        return "updated"

    monkeypatch.setattr(catalog_sync, "_sync_one", fake_sync_one)
    monkeypatch.setattr(catalog_sync.time, "sleep", lambda _seconds: None)

    result = catalog_sync._sync(
        "coupang",
        [
            {"platform_id": "1", "name": "상품1"},
            {"platform_id": "2", "name": "상품2"},
        ],
    )

    assert result["ok"] is True
    assert result["updated"] == 2
    assert result["failed"] == 0
    assert calls == {"1": 2, "2": 1}


def test_sync_continues_after_one_item_exhausts_lock_retries(monkeypatch):
    def fake_sync_one(platform, item):
        if item["platform_id"] == "bad":
            raise _locked_error()
        return "linked"

    monkeypatch.setattr(catalog_sync, "_sync_one", fake_sync_one)
    monkeypatch.setattr(catalog_sync.time, "sleep", lambda _seconds: None)

    result = catalog_sync._sync(
        "smartstore",
        [
            {"platform_id": "bad", "name": "잠긴상품"},
            {"platform_id": "good", "name": "정상상품"},
        ],
    )

    assert result["ok"] is False
    assert result["failed"] == 1
    assert result["linked"] == 1
    assert result["total_found"] == 2
    assert "bad" in result["error"]
