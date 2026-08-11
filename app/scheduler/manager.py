"""APScheduler 싱글톤 관리자 — DB 기반 작업 설정, 실행 로깅."""
from __future__ import annotations
import json
import logging
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.db import get_db, ScheduledJob, JobRunLog
from app.scheduler.jobs import DEFAULT_JOBS, JOB_FUNCTIONS

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_scheduler_instance: "SchedulerManager | None" = None


class SchedulerManager:
    """APScheduler BackgroundScheduler 래퍼.

    - DB의 scheduled_jobs 테이블을 단일 진실 소스로 사용
    - enabled=True 작업을 스케줄러에 등록
    - 작업 실행 전후 job_run_logs에 기록
    """

    def __init__(self):
        s = get_settings()
        self.tz = s.scheduler_timezone
        self._scheduler = BackgroundScheduler(timezone=self.tz)
        self._ensure_default_jobs()
        self._load_jobs()
        if s.scheduler_enabled:
            self._scheduler.start()
            logger.info("스케줄러 시작 (timezone=%s)", self.tz)

    # ── DB 초기화 ──────────────────────────────────────────────────────────

    def _ensure_default_jobs(self) -> None:
        """DB에 기본 작업이 없으면 DEFAULT_JOBS로 초기화."""
        with get_db() as db:
            for job_id, cfg in DEFAULT_JOBS.items():
                existing = db.query(ScheduledJob).filter_by(job_id=job_id).first()
                if not existing:
                    db.add(ScheduledJob(
                        job_id=job_id,
                        name=cfg["name"],
                        description=cfg["description"],
                        cron_expr=cfg["cron_expr"],
                        enabled=cfg["enabled"],
                    ))
            db.commit()

    # ── 스케줄러 등록 ──────────────────────────────────────────────────────

    def _load_jobs(self) -> None:
        """DB의 enabled 작업을 모두 스케줄러에 등록."""
        with get_db() as db:
            jobs = db.query(ScheduledJob).filter_by(enabled=True).all()
            for job in jobs:
                self._register(job.job_id, job.cron_expr)

    def _register(self, job_id: str, cron_expr: str) -> None:
        """APScheduler에 작업 등록 (이미 있으면 교체)."""
        fn = JOB_FUNCTIONS.get(job_id)
        if not fn:
            logger.warning("알 수 없는 job_id: %s", job_id)
            return

        parts = cron_expr.strip().split()
        if len(parts) != 5:
            logger.error("잘못된 cron 표현식 [%s]: %s", job_id, cron_expr)
            return

        minute, hour, day, month, day_of_week = parts

        # 이미 등록된 경우 제거 후 재등록
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

        def _wrapper(jid=job_id, func=fn):
            self._run_job(jid, func)

        self._scheduler.add_job(
            _wrapper,
            trigger=CronTrigger(
                minute=minute, hour=hour,
                day=day, month=month,
                day_of_week=day_of_week,
                timezone=self.tz,
            ),
            id=job_id,
            replace_existing=True,
            misfire_grace_time=3600,    # 최대 1시간 지연 허용
        )

        # next_run_at DB 업데이트
        try:
            job = self._scheduler.get_job(job_id)
            if job and job.next_run_time:
                with get_db() as db:
                    row = db.query(ScheduledJob).filter_by(job_id=job_id).first()
                    if row:
                        row.next_run_at = job.next_run_time.replace(tzinfo=None)
                        db.commit()
        except Exception:
            pass

    def _unregister(self, job_id: str) -> None:
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

    # ── 작업 실행 ──────────────────────────────────────────────────────────

    def _run_job(self, job_id: str, func) -> None:
        """작업 실행 + 로그 기록."""
        run_log_id: int | None = None
        started = datetime.utcnow()

        with get_db() as db:
            row = db.query(ScheduledJob).filter_by(job_id=job_id).first()
            if row:
                row.last_status = "running"
                row.last_run_at = started
                db.commit()

            log = JobRunLog(job_id=job_id, started_at=started, status="running")
            db.add(log)
            db.commit()
            db.refresh(log)
            run_log_id = log.id

        try:
            result = func()
            result_json = json.dumps(result or {}, ensure_ascii=False)
            status = "ok"
            error = ""
        except Exception as exc:
            result_json = "{}"
            status = "failed"
            error = str(exc)[:500]
            logger.error("스케줄 작업 실패 [%s]: %s", job_id, exc, exc_info=True)

        finished = datetime.utcnow()
        with get_db() as db:
            if run_log_id:
                log = db.query(JobRunLog).filter_by(id=run_log_id).first()
                if log:
                    log.finished_at = finished
                    log.status = status
                    log.result = result_json
                    log.error = error

            row = db.query(ScheduledJob).filter_by(job_id=job_id).first()
            if row:
                row.last_status = status
                row.last_error = error
                row.run_count = (row.run_count or 0) + 1

                # next_run_at 갱신
                try:
                    job = self._scheduler.get_job(job_id)
                    if job and job.next_run_time:
                        row.next_run_at = job.next_run_time.replace(tzinfo=None)
                except Exception:
                    pass

            db.commit()

    # ── 외부 API ──────────────────────────────────────────────────────────

    def run_now(self, job_id: str) -> dict:
        """즉시 실행 (별도 스레드)."""
        fn = JOB_FUNCTIONS.get(job_id)
        if not fn:
            return {"status": "error", "error": f"알 수 없는 job: {job_id}"}
        t = threading.Thread(target=self._run_job, args=(job_id, fn), daemon=True)
        t.start()
        return {"status": "ok", "message": f"{job_id} 실행 시작됨"}

    def toggle(self, job_id: str, enabled: bool) -> dict:
        """작업 활성/비활성 전환."""
        with get_db() as db:
            row = db.query(ScheduledJob).filter_by(job_id=job_id).first()
            if not row:
                return {"status": "error", "error": "작업 없음"}
            row.enabled = enabled
            db.commit()

        if enabled:
            with get_db() as db:
                row = db.query(ScheduledJob).filter_by(job_id=job_id).first()
                self._register(job_id, row.cron_expr)
        else:
            self._unregister(job_id)

        return {"status": "ok"}

    def update_cron(self, job_id: str, cron_expr: str) -> dict:
        """cron 표현식 변경 후 재등록."""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return {"status": "error", "error": "cron 형식 오류 (예: 0 3 * * *)"}

        with get_db() as db:
            row = db.query(ScheduledJob).filter_by(job_id=job_id).first()
            if not row:
                return {"status": "error", "error": "작업 없음"}
            row.cron_expr = cron_expr
            db.commit()
            if row.enabled:
                self._register(job_id, cron_expr)

        return {"status": "ok"}

    def get_status(self) -> dict:
        """스케줄러 전체 상태 반환."""
        running = self._scheduler.running
        jobs_info = []
        with get_db() as db:
            rows = db.query(ScheduledJob).order_by(ScheduledJob.id).all()
            for row in rows:
                aps_job = self._scheduler.get_job(row.job_id) if running else None
                next_run = None
                if aps_job and aps_job.next_run_time:
                    next_run = aps_job.next_run_time.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M")

                jobs_info.append({
                    "job_id": row.job_id,
                    "name": row.name,
                    "description": row.description,
                    "cron_expr": row.cron_expr,
                    "enabled": row.enabled,
                    "last_status": row.last_status,
                    "last_error": row.last_error,
                    "run_count": row.run_count,
                    "last_run_at": row.last_run_at.strftime("%Y-%m-%d %H:%M") if row.last_run_at else "",
                    "next_run_at": next_run or (row.next_run_at.strftime("%Y-%m-%d %H:%M") if row.next_run_at else ""),
                })

        return {
            "running": running,
            "timezone": self.tz,
            "total_jobs": len(jobs_info),
            "enabled_jobs": sum(1 for j in jobs_info if j["enabled"]),
            "jobs": jobs_info,
        }

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)


# ── 싱글톤 접근 ───────────────────────────────────────────────────────────────

def get_scheduler() -> SchedulerManager:
    global _scheduler_instance
    if _scheduler_instance is None:
        with _lock:
            if _scheduler_instance is None:
                _scheduler_instance = SchedulerManager()
    return _scheduler_instance
