from types import SimpleNamespace

from app.notify.events import EventType
from app.os.scheduler import DEFAULT_JOBS
from app.os.tasks import TASK_TIMEOUT_SECONDS
import app.pricing.watch as watch


def test_pricing_watch_is_safe_and_disabled_by_default():
    spec = DEFAULT_JOBS["pricing_watch"]
    assert spec["enabled"] is False
    assert spec["queue"] == "sync"
    assert spec["default_minutes"] == 360
    assert spec["payload"]["live"] is True
    assert TASK_TIMEOUT_SECONDS["pricing_watch"] == 7200
    assert EventType.PRICE_MARGIN_ALERT.value == "price_margin_alert"


def test_pricing_watch_never_mutates_remote_prices(monkeypatch):
    row = SimpleNamespace(name="테스트상품")
    monkeypatch.setattr(watch, "rebuild_supplier_mappings", lambda: {"matched": 1})
    monkeypatch.setattr(watch, "refresh_supplier_prices", lambda max_items: {"refreshed": 1})
    monkeypatch.setattr(watch, "load_price_rows", lambda live=True: [row])
    monkeypatch.setattr(watch, "get_policy", lambda: SimpleNamespace(target_margin_rate=0.36))
    monkeypatch.setattr(
        watch,
        "sync_approval_queue",
        lambda rows, target: {
            "created": 0,
            "updated": 1,
            "escalated": 0,
            "resolved": 0,
            "pending": 1,
            "notify_items": [],
        },
    )
    monkeypatch.setattr(watch, "notify", lambda **kwargs: (_ for _ in ()).throw(AssertionError("notify should not run")))

    result = watch.run_pricing_watch(max_supplier_items=10, live=True)

    assert result["ok"] is True
    assert result["remote_price_mutations"] == 0
    assert result["notification_sent"] is False
