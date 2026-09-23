from app.scheduler.jobs import DEFAULT_JOBS, JOB_FUNCTIONS


def test_price_guard_monitor_is_registered_but_disabled_by_default():
    cfg = DEFAULT_JOBS["price_guard_monitor"]
    assert cfg["enabled"] is False
    assert cfg["cron_expr"] == "15 */4 * * *"
    assert "승인 대기열" in cfg["description"]
    assert JOB_FUNCTIONS["price_guard_monitor"].__name__ == "job_price_guard_monitor"


def test_legacy_price_sync_remains_separate_from_approval_monitor():
    assert "price_sync" in DEFAULT_JOBS
    assert "price_guard_monitor" in DEFAULT_JOBS
    assert JOB_FUNCTIONS["price_sync"] is not JOB_FUNCTIONS["price_guard_monitor"]
