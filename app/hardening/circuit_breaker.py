"""Circuit Breaker — 3-state (CLOSED / OPEN / HALF_OPEN), DB 영속화."""
from __future__ import annotations
import logging
import threading
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED    = "closed"     # 정상 — 호출 통과
    OPEN      = "open"       # 차단 — 빠른 실패
    HALF_OPEN = "half_open"  # 복구 탐색 — 한 번 허용


class CircuitOpenError(RuntimeError):
    """Circuit이 OPEN 상태일 때 발생. 호출자는 캐시/fallback 사용."""


# ── 서비스별 기본 설정 ────────────────────────────────────────────────────────

_SERVICE_CONFIG: dict[str, dict] = {
    "coupang_api":      {"failure_threshold": 5, "recovery_timeout": 120},
    "smartstore_api":   {"failure_threshold": 5, "recovery_timeout": 120},
    "onchannel_scrape": {"failure_threshold": 3, "recovery_timeout": 180},
    "naver_api":        {"failure_threshold": 5, "recovery_timeout": 60},
    "telegram_bot":     {"failure_threshold": 3, "recovery_timeout": 60},
    "claude_ai":        {"failure_threshold": 3, "recovery_timeout": 30},
}


class CircuitBreaker:
    """스레드 안전, DB 상태 영속화 Circuit Breaker."""

    def __init__(self, service: str, failure_threshold: int = 5, recovery_timeout: int = 120):
        self.service = service
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout

        self._lock           = threading.Lock()
        self._state          = CircuitState.CLOSED
        self._failure_count  = 0
        self._last_failure: datetime | None = None
        self._opened_at: datetime | None    = None

        self._load_from_db()

    # ── 상태 전이 ────────────────────────────────────────────────────────────

    def _should_attempt_reset(self) -> bool:
        if self._opened_at is None:
            return True
        elapsed = (datetime.utcnow() - self._opened_at).total_seconds()
        return elapsed >= self.recovery_timeout

    def _on_success(self) -> None:
        with self._lock:
            if self._state != CircuitState.CLOSED or self._failure_count > 0:
                old = self._state
                self._state         = CircuitState.CLOSED
                self._failure_count = 0
                self._opened_at     = None
                self._persist()
                if old != CircuitState.CLOSED:
                    logger.info("Circuit CLOSED [%s]", self.service)

    def _on_failure(self, exc: Exception) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure   = datetime.utcnow()
            if self._failure_count >= self.failure_threshold and self._state != CircuitState.OPEN:
                self._state     = CircuitState.OPEN
                self._opened_at = datetime.utcnow()
                self._persist()
                logger.warning(
                    "Circuit OPEN [%s] after %d failures — %s",
                    self.service, self._failure_count, exc,
                )
            else:
                self._persist()

    # ── 공개 API ─────────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def call(self, fn: Callable[[], T]) -> T:
        """fn 을 Circuit Breaker 보호 하에 실행한다."""
        with self._lock:
            current = self._state

        if current == CircuitState.OPEN:
            if self._should_attempt_reset():
                with self._lock:
                    self._state = CircuitState.HALF_OPEN
                logger.info("Circuit HALF_OPEN [%s] — 복구 탐색", self.service)
            else:
                secs = 0
                if self._opened_at:
                    secs = int(self.recovery_timeout - (datetime.utcnow() - self._opened_at).total_seconds())
                raise CircuitOpenError(
                    f"[{self.service}] circuit OPEN — {max(0, secs)}초 후 재시도"
                )

        try:
            result = fn()
            self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as exc:
            self._on_failure(exc)
            raise

    def reset(self) -> None:
        """수동 리셋 — 관리자 GUI에서 호출."""
        with self._lock:
            self._state         = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at     = None
            self._last_failure  = None
            self._persist()
        logger.info("Circuit manually RESET [%s]", self.service)

    def status_dict(self) -> dict:
        with self._lock:
            return {
                "service":         self.service,
                "state":           self._state.value,
                "failure_count":   self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "last_failure":    self._last_failure.isoformat() if self._last_failure else "",
                "opened_at":       self._opened_at.isoformat() if self._opened_at else "",
            }

    # ── DB 영속화 ─────────────────────────────────────────────────────────────

    def _load_from_db(self) -> None:
        try:
            from app.db import get_db, CircuitBreakerState
            with get_db() as db:
                row = db.query(CircuitBreakerState).filter_by(service=self.service).first()
                if row:
                    self._state         = CircuitState(row.state)
                    self._failure_count = row.failure_count
                    self._last_failure  = row.last_failure_at
                    self._opened_at     = row.opened_at
        except Exception:
            pass  # DB 미준비 시 메모리 기본값 사용

    def _persist(self) -> None:
        try:
            from app.db import get_db, CircuitBreakerState
            with get_db() as db:
                row = db.query(CircuitBreakerState).filter_by(service=self.service).first()
                if row:
                    row.state          = self._state.value
                    row.failure_count  = self._failure_count
                    row.last_failure_at = self._last_failure
                    row.opened_at      = self._opened_at
                    row.updated_at     = datetime.utcnow()
                else:
                    db.add(CircuitBreakerState(
                        service       = self.service,
                        state         = self._state.value,
                        failure_count = self._failure_count,
                        last_failure_at = self._last_failure,
                        opened_at     = self._opened_at,
                    ))
                db.commit()
        except Exception as exc:
            logger.debug("CB persist 실패: %s", exc)


# ── 레지스트리 ────────────────────────────────────────────────────────────────

_registry: dict[str, CircuitBreaker] = {}
_reg_lock = threading.Lock()


def get_circuit_breaker(service: str) -> CircuitBreaker:
    """서비스명으로 CircuitBreaker 싱글톤을 반환한다."""
    if service not in _registry:
        with _reg_lock:
            if service not in _registry:
                cfg = _SERVICE_CONFIG.get(service, {})
                _registry[service] = CircuitBreaker(
                    service,
                    failure_threshold=cfg.get("failure_threshold", 5),
                    recovery_timeout=cfg.get("recovery_timeout", 120),
                )
    return _registry[service]


def all_breakers() -> list[dict]:
    """등록된 모든 circuit breaker 상태 목록."""
    # 미등록 서비스도 초기화
    for svc in _SERVICE_CONFIG:
        get_circuit_breaker(svc)
    return [cb.status_dict() for cb in _registry.values()]
