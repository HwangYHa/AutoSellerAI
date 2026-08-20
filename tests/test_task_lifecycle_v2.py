from __future__ import annotations

from app.os.task_recovery import STALE_RUNNING_MINUTES
from app.os.tasks import (
    RQ_FAILURE_TTL_SECONDS,
    RQ_RESULT_TTL_SECONDS,
    TASK_TIMEOUT_SECONDS,
)


def test_order_sync_timeout_exceeds_stale_running_window():
    # A legitimate order sync must not be killed by RQ before recovery even
    # considers it stale. The old 1800s timeout violated this invariant.
    assert TASK_TIMEOUT_SECONDS["order_sync"] > STALE_RUNNING_MINUTES * 60


def test_rq_terminal_records_outlive_recovery_window():
    # Recovery needs terminal RQ metadata long enough to reconcile the DB
    # journal instead of misclassifying a completed/failed job as missing.
    assert RQ_RESULT_TTL_SECONDS > STALE_RUNNING_MINUTES * 60
    assert RQ_FAILURE_TTL_SECONDS > RQ_RESULT_TTL_SECONDS


def test_dangerous_tasks_keep_bounded_timeouts():
    # Marketplace/supplier mutations remain bounded and are never treated as
    # safe automatic recovery work.
    assert TASK_TIMEOUT_SECONDS["listing_publish"] <= 1800
    assert TASK_TIMEOUT_SECONDS["supplier_order"] <= 1800
