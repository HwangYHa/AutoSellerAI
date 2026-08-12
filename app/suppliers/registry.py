"""공급사 어댑터 레지스트리.

새 공급사 추가 방법:
  1) app/suppliers/adapter_<name>.py 에 SupplierAdapter 구현
  2) _ADAPTER_FACTORIES 에 항목 추가
  3) 끝 — pipeline.py 수정 불필요
"""
from __future__ import annotations

import logging
from typing import Callable

from app.suppliers.base import SupplierAdapter, NormalizedProduct

logger = logging.getLogger(__name__)

# ── 어댑터 팩토리 등록 ──────────────────────────────────────────────────────────
# lazy-import: 실제 호출 시점까지 import 지연 (실패해도 다른 어댑터 영향 없음)

def _load_domeggook():
    from app.suppliers.adapter_domeggook import DomeggookAdapter
    return DomeggookAdapter()

def _load_domemai():
    from app.suppliers.adapter_domemai import DomemaiAdapter
    return DomemaiAdapter()

def _load_onchannel():
    from app.suppliers.adapter_onchannel import OnchanelAdapter
    return OnchanelAdapter()

def _load_ownerclan():
    from app.suppliers.adapter_ownerclan import OwnerClanAdapter
    return OwnerClanAdapter()


_ADAPTER_FACTORIES: dict[str, Callable[[], SupplierAdapter]] = {
    "domeggook": _load_domeggook,
    "domemai":   _load_domemai,
    "onchannel": _load_onchannel,
    "ownerclan": _load_ownerclan,
}

_instances: dict[str, SupplierAdapter] = {}


def get_adapter(supplier_id: str) -> SupplierAdapter | None:
    """supplier_id로 어댑터 인스턴스를 반환 (싱글턴)."""
    if supplier_id in _instances:
        return _instances[supplier_id]

    factory = _ADAPTER_FACTORIES.get(supplier_id)
    if not factory:
        logger.warning("알 수 없는 공급사: %s", supplier_id)
        return None

    try:
        adapter = factory()
        _instances[supplier_id] = adapter
        return adapter
    except Exception as exc:
        logger.error("어댑터 로드 실패 [%s]: %s", supplier_id, exc)
        return None


def get_available_adapters() -> list[SupplierAdapter]:
    """API 키가 설정된 활성 어댑터 목록 반환."""
    result = []
    for sid in _ADAPTER_FACTORIES:
        adapter = get_adapter(sid)
        if adapter and adapter.is_available():
            result.append(adapter)
    return result


def get_all_adapters() -> list[SupplierAdapter]:
    """설정 여부와 무관하게 모든 등록된 어댑터 반환."""
    result = []
    for sid in _ADAPTER_FACTORIES:
        adapter = get_adapter(sid)
        if adapter:
            result.append(adapter)
    return result


def search_all(keyword: str, limit_per_supplier: int = 50,
               min_price: int = 3000, moq: int = 1,
               suppliers: list[str] | None = None) -> list[NormalizedProduct]:
    """모든 활성 어댑터에서 동시 검색 후 통합 목록 반환.

    suppliers 지정 시 해당 공급사만 검색.
    """
    target_ids = suppliers or list(_ADAPTER_FACTORIES.keys())
    results: list[NormalizedProduct] = []

    for sid in target_ids:
        adapter = get_adapter(sid)
        if not adapter or not adapter.is_available():
            logger.debug("어댑터 비활성 — 건너뜀: %s", sid)
            continue
        try:
            items = adapter.search(keyword, limit=limit_per_supplier,
                                   min_price=min_price, moq=moq)
            results.extend(items)
            logger.debug("수집 [%s/%s]: %d개", sid, keyword, len(items))
        except Exception as exc:
            logger.warning("수집 실패 [%s/%s]: %s", sid, keyword, exc)

    return results


def list_registered() -> list[dict]:
    """등록된 모든 어댑터 메타 정보 반환 (GUI/설정 화면용)."""
    info = []
    for sid in _ADAPTER_FACTORIES:
        adapter = get_adapter(sid)
        info.append({
            "supplier_id": sid,
            "display_name": getattr(adapter, "display_name", sid) if adapter else sid,
            "available": adapter.is_available() if adapter else False,
        })
    return info
