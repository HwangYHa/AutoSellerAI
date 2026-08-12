"""공급사 어댑터 레지스트리.

새 공급사 추가 방법:
  1) app/suppliers/adapter_<name>.py 에 SupplierAdapter 구현
  2) _ADAPTER_FACTORIES 에 항목 추가
  3) 끝 — pipeline.py 수정 불필요

모든 어댑터는 여기에서 이미지 보완 계층을 통과한다.
- 검색 목록: 공급사 응답/raw_data 안의 이미지 태그만 보완 (외부 페이지 추가 요청 없음)
- 단건 상세: 설정에 따라 원본 상품 HTML까지 조회하여 img/src/data-src/srcset 등을 보완
"""
from __future__ import annotations

import logging
from typing import Callable

from app.suppliers.base import SupplierAdapter, NormalizedProduct

logger = logging.getLogger(__name__)


def _enrich_images(product: NormalizedProduct | None, *, fetch_page: bool) -> NormalizedProduct | None:
    if product is None:
        return None
    try:
        from app.media.product_images import collect_product_images
        collected = collect_product_images(product, fetch_page=fetch_page)
        product.images = collected.images
        product.detail_images = collected.detail_images
        if isinstance(product.raw_data, dict):
            product.raw_data.setdefault("image_collection", {})
            product.raw_data["image_collection"].update({
                "source": collected.source,
                "fetched_html": collected.fetched_html,
                "image_count": len(collected.images),
                "detail_image_count": len(collected.detail_images),
            })
    except Exception as exc:
        # 이미지 보완 오류 때문에 상품 수집 전체가 실패하면 안 된다.
        logger.debug("상품 이미지 보완 실패 [%s/%s]: %s", product.supplier_id, product.raw_id, exc)
    return product


class _ImageAwareAdapter:
    """실제 공급처 어댑터 앞에 붙는 공통 이미지 보완 프록시."""

    def __init__(self, inner: SupplierAdapter):
        self._inner = inner
        self.supplier_id = inner.supplier_id
        self.display_name = inner.display_name

    def is_available(self) -> bool:
        return self._inner.is_available()

    def search(self, keyword: str, page: int = 1, limit: int = 50,
               min_price: int = 3000, moq: int = 1) -> list[NormalizedProduct]:
        items = self._inner.search(keyword, page=page, limit=limit, min_price=min_price, moq=moq)
        return [_enrich_images(p, fetch_page=False) for p in items if p is not None]

    def get_product(self, product_id: str) -> NormalizedProduct | None:
        product = self._inner.get_product(product_id)
        try:
            from app.config import get_settings
            fetch_page = bool(get_settings().image_source_page_fetch)
        except Exception:
            fetch_page = True
        return _enrich_images(product, fetch_page=fetch_page)

    def __getattr__(self, name):
        return getattr(self._inner, name)


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
    """supplier_id로 이미지 보완이 적용된 어댑터 인스턴스를 반환 (싱글턴)."""
    if supplier_id in _instances:
        return _instances[supplier_id]

    factory = _ADAPTER_FACTORIES.get(supplier_id)
    if not factory:
        logger.warning("알 수 없는 공급사: %s", supplier_id)
        return None

    try:
        adapter = _ImageAwareAdapter(factory())
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
