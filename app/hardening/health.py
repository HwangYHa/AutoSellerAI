"""Health Check Engine — DB·Telegram·API·스케줄러·디스크."""
from __future__ import annotations
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class HealthResult:
    service:    str
    status:     str        # ok | degraded | down | unknown
    latency_ms: int = 0
    detail:     str = ""
    error:      str = ""
    checked_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "service":    self.service,
            "status":     self.status,
            "latency_ms": self.latency_ms,
            "detail":     self.detail,
            "error":      self.error,
            "checked_at": self.checked_at.strftime("%Y-%m-%d %H:%M:%S"),
        }


def _measure(fn) -> tuple[bool, int, str, str]:
    """fn() 실행 후 (ok, latency_ms, detail, error)."""
    start = time.monotonic()
    try:
        detail = fn() or ""
        ms = int((time.monotonic() - start) * 1000)
        return True, ms, str(detail), ""
    except Exception as exc:
        ms = int((time.monotonic() - start) * 1000)
        return False, ms, "", str(exc)[:200]


# ── 개별 체크 함수 ────────────────────────────────────────────────────────────

def check_database() -> HealthResult:
    def _fn():
        from app.db import get_db, Product
        with get_db() as db:
            cnt = db.query(Product).count()
        return f"products={cnt}"

    ok, ms, detail, err = _measure(_fn)
    status = "ok" if ok else "down"
    if ok and ms > 500:
        status = "degraded"
    return HealthResult("database", status, ms, detail, err)


def check_telegram() -> HealthResult:
    def _fn():
        from app.config import get_settings
        s = get_settings()
        if not s.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN 미설정")
        import requests
        r = requests.get(
            f"https://api.telegram.org/bot{s.telegram_bot_token}/getMe",
            timeout=8,
        )
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description", "Bot 오류"))
        return f"@{data['result'].get('username', '?')}"

    ok, ms, detail, err = _measure(_fn)
    return HealthResult("telegram", "ok" if ok else "down", ms, detail, err)


def check_coupang_api() -> HealthResult:
    def _fn():
        from app.config import get_settings
        s = get_settings()
        if not (s.coupang_access_key and s.coupang_secret_key and s.coupang_vendor_id):
            raise ValueError("Coupang API 자격증명 미설정")
        return f"vendor={s.coupang_vendor_id}"

    ok, ms, detail, err = _measure(_fn)
    status = "ok" if ok else "down"
    return HealthResult("coupang_api", status, ms, detail, err)


def check_smartstore_api() -> HealthResult:
    def _fn():
        from app.config import get_settings
        s = get_settings()
        if not (s.naver_client_id and s.naver_client_secret):
            raise ValueError("SmartStore API 자격증명 미설정")
        return f"client={s.naver_client_id[:8]}..."

    ok, ms, detail, err = _measure(_fn)
    return HealthResult("smartstore_api", "ok" if ok else "down", ms, detail, err)


def check_naver_api() -> HealthResult:
    def _fn():
        from app.config import get_settings
        s = get_settings()
        if not (s.naver_search_client_id and s.naver_search_client_secret):
            raise ValueError("Naver Search API 자격증명 미설정")
        import httpx
        r = httpx.get(
            "https://openapi.naver.com/v1/search/shop.json",
            params={"query": "test", "display": 1},
            headers={
                "X-Naver-Client-Id":     s.naver_search_client_id,
                "X-Naver-Client-Secret": s.naver_search_client_secret,
            },
            timeout=8,
        )
        if r.status_code == 200:
            return "API 응답 정상"
        raise RuntimeError(f"HTTP {r.status_code}")

    ok, ms, detail, err = _measure(_fn)
    status = "ok" if ok else ("degraded" if "401" in err or "403" in err else "down")
    return HealthResult("naver_api", status, ms, detail, err)


def check_claude_ai() -> HealthResult:
    def _fn():
        from app.config import get_settings
        s = get_settings()
        if not s.claude_api_key:
            raise ValueError("CLAUDE_API_KEY 미설정")
        return f"model={s.claude_model}"

    ok, ms, detail, err = _measure(_fn)
    return HealthResult("claude_ai", "ok" if ok else "down", ms, detail, err)


def check_scheduler() -> HealthResult:
    def _fn():
        from app.scheduler.manager import get_scheduler
        sched = get_scheduler()
        status = sched.get_status()
        enabled = status["enabled_jobs"]
        total   = status["total_jobs"]
        if not status["running"]:
            raise RuntimeError("스케줄러 중지됨")
        return f"running · {enabled}/{total}개 활성"

    ok, ms, detail, err = _measure(_fn)
    return HealthResult("scheduler", "ok" if ok else "degraded", ms, detail, err)


def check_disk() -> HealthResult:
    def _fn():
        usage = shutil.disk_usage(os.path.abspath("data"))
        pct = usage.used / usage.total * 100
        free_gb = usage.free / (1024 ** 3)
        if pct > 90:
            raise RuntimeError(f"디스크 사용률 {pct:.1f}% — 여유 {free_gb:.1f}GB")
        return f"사용 {pct:.1f}% · 여유 {free_gb:.1f}GB"

    ok, ms, detail, err = _measure(_fn)
    status = "ok" if ok else ("degraded" if "90" in err else "down")
    return HealthResult("disk", status, ms, detail, err)


# ── 전체 체크 ─────────────────────────────────────────────────────────────────

_CHECK_FUNCTIONS = [
    check_database,
    check_telegram,
    check_coupang_api,
    check_smartstore_api,
    check_naver_api,
    check_claude_ai,
    check_scheduler,
    check_disk,
]


def run_all_checks(save_logs: bool = True) -> dict:
    """모든 헬스 체크를 실행하고 결과를 반환한다."""
    results = []
    for fn in _CHECK_FUNCTIONS:
        try:
            r = fn()
        except Exception as exc:
            r = HealthResult(fn.__name__.replace("check_", ""), "unknown", 0, "", str(exc))
        results.append(r)

    if save_logs:
        _save_logs(results)

    ok_count   = sum(1 for r in results if r.status == "ok")
    down_count = sum(1 for r in results if r.status == "down")
    deg_count  = sum(1 for r in results if r.status == "degraded")

    overall = "ok"
    if down_count > 0:
        overall = "down" if down_count >= 2 else "degraded"
    elif deg_count > 0:
        overall = "degraded"

    return {
        "overall":    overall,
        "ok":         ok_count,
        "degraded":   deg_count,
        "down":       down_count,
        "total":      len(results),
        "checked_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "services":   [r.to_dict() for r in results],
    }


def _save_logs(results: list[HealthResult]) -> None:
    try:
        from app.db import get_db, HealthCheckLog
        with get_db() as db:
            for r in results:
                db.add(HealthCheckLog(
                    service    = r.service,
                    status     = r.status,
                    latency_ms = r.latency_ms,
                    detail     = r.detail[:200],
                    error      = r.error[:300],
                ))
            db.commit()
    except Exception as exc:
        logger.debug("health log 저장 실패: %s", exc)
