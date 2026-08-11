"""Rate Limiter — Token Bucket, 서비스별 req/s 제한, 스레드 안전."""
from __future__ import annotations
import logging
import threading
import time

logger = logging.getLogger(__name__)


# ── 서비스별 기본 설정: (rate req/s, burst capacity) ─────────────────────────

_SERVICE_LIMITS: dict[str, tuple[float, int]] = {
    "coupang_api":      (3.0,  10),   # 3 req/s, burst 10
    "smartstore_api":   (5.0,  15),   # 5 req/s, burst 15
    "onchannel_scrape": (0.5,   3),   # 0.5 req/s (2초당 1회), burst 3
    "naver_api":        (10.0, 30),   # 10 req/s, burst 30
    "telegram_bot":     (20.0, 30),   # 30 msg/s 제한보다 여유
    "claude_ai":        (2.0,   5),   # 2 req/s, burst 5
}


class TokenBucket:
    """Token Bucket 알고리즘 — 스레드 안전."""

    def __init__(self, rate: float, capacity: int, service: str = ""):
        self.rate     = rate       # tokens/second 충전 속도
        self.capacity = capacity   # 최대 토큰 (burst)
        self.service  = service
        self._tokens     = float(capacity)
        self._last_refill = time.monotonic()
        self._lock    = threading.Lock()

    def _refill(self) -> None:
        now     = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens     = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    def acquire(self, timeout: float = 10.0) -> bool:
        """토큰 1개를 획득한다. timeout 초 내 획득 불가 시 False."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
            # 다음 토큰 충전 예상 대기
            wait = 1.0 / self.rate if self.rate > 0 else 1.0
            time.sleep(min(wait, 0.1))
        logger.warning("Rate limit timeout [%s] after %.1fs", self.service, timeout)
        return False

    def available(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    @property
    def wait_seconds(self) -> float:
        """다음 토큰까지 대기 시간 (초)."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                return 0.0
            return (1.0 - self._tokens) / self.rate

    def status_dict(self) -> dict:
        with self._lock:
            self._refill()
            return {
                "service":    self.service,
                "rate":       self.rate,
                "capacity":   self.capacity,
                "tokens":     round(self._tokens, 2),
                "wait_sec":   round(max(0.0, (1.0 - self._tokens) / self.rate) if self._tokens < 1 else 0.0, 3),
            }


# ── 레지스트리 ────────────────────────────────────────────────────────────────

_registry: dict[str, TokenBucket] = {}
_reg_lock = threading.Lock()


def get_rate_limiter(service: str) -> TokenBucket:
    """서비스명으로 TokenBucket 싱글톤을 반환한다."""
    if service not in _registry:
        with _reg_lock:
            if service not in _registry:
                rate, cap = _SERVICE_LIMITS.get(service, (5.0, 10))
                _registry[service] = TokenBucket(rate, cap, service)
    return _registry[service]


def all_limiters() -> list[dict]:
    """모든 rate limiter 상태 목록."""
    for svc in _SERVICE_LIMITS:
        get_rate_limiter(svc)
    return [rl.status_dict() for rl in _registry.values()]
