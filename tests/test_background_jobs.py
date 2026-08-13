import time

from app.services.background_jobs import clear_background_job, get_background_job, submit_background_job


def _wait(job_id: str, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        row = get_background_job(job_id)
        if row and row["status"] in {"success", "failed"}:
            return row
        time.sleep(0.02)
    return get_background_job(job_id)


def test_background_job_returns_result_without_ui_dependency():
    job_id = submit_background_job("sum", lambda a, b: {"value": a + b}, 2, 3)
    row = _wait(job_id)
    assert row is not None
    assert row["status"] == "success"
    assert row["result"] == {"value": 5}
    assert row["error"] == ""
    clear_background_job(job_id)
    assert get_background_job(job_id) is None


def test_background_job_captures_failure():
    def fail():
        raise RuntimeError("boom")

    job_id = submit_background_job("fail", fail)
    row = _wait(job_id)
    assert row is not None
    assert row["status"] == "failed"
    assert "RuntimeError: boom" in row["error"]
