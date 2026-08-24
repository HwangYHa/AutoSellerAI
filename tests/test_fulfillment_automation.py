from types import SimpleNamespace

from app.os import fulfillment_automation as fa
from app.os.scheduler import SAFE_JOBS
from app.os.tasks import TASK_TIMEOUT_SECONDS, _task_callable


def test_auto_purchase_is_off_unless_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(
        fa,
        "get_settings",
        lambda: SimpleNamespace(fulfillment_auto_purchase_enabled=False),
    )
    result = fa.evaluate_auto_purchase_policy(123)
    assert result.allowed is False
    assert result.code == "AUTO_PURCHASE_DISABLED"


def test_near_realtime_order_and_fulfillment_schedule_exists():
    assert SAFE_JOBS["order_sync"]["default_minutes"] == 1
    assert SAFE_JOBS["fulfillment_cycle"]["default_minutes"] == 1
    assert SAFE_JOBS["fulfillment_cycle"]["queue"] == "automation"


def test_fulfillment_cycle_is_registered_as_background_task():
    assert TASK_TIMEOUT_SECONDS["fulfillment_cycle"] == 1800
    assert callable(_task_callable("fulfillment_cycle"))
