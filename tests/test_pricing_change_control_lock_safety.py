from __future__ import annotations

import inspect

from app.pricing import approval_queue, change_control, service


def test_pricing_change_control_writes_use_writer_guard():
    create_batch = inspect.getsource(change_control._create_batch)
    update_item = inspect.getsource(change_control._update_batch_item)
    finish_batch = inspect.getsource(change_control._finish_batch)
    rollback = inspect.getsource(change_control._record_rollback)

    for source in (create_batch, update_item, finish_batch, rollback):
        assert "sqlite_writer_guard" in source
        assert "retry_sqlite_write" in source


def test_price_change_log_write_uses_writer_guard():
    source = inspect.getsource(service._log_change)
    assert "sqlite_writer_guard" in source
    assert "retry_sqlite_write" in source


def test_pricing_approval_writes_use_writer_guard():
    sync_source = inspect.getsource(approval_queue.sync_approval_queue)
    dismiss_source = inspect.getsource(approval_queue.dismiss_approval)
    applied_source = inspect.getsource(approval_queue.mark_approval_queue_applied)

    assert "sqlite_writer_guard" in sync_source
    assert "sqlite_writer_guard" in dismiss_source
    assert "sqlite_writer_guard" in applied_source


def test_apply_guarded_batch_fails_closed_when_batch_journal_is_locked():
    source = inspect.getsource(change_control.apply_guarded_batch)
    assert "except OperationalError" in source
    assert '"success": 0' in source
    assert '"failed": len(rows)' in source
