"""온채널 공급사 어댑터 (Layer 1).

[온채널 특성]
  - 중간 구조: 공급사 → 온채널 → 판매자  ← 다른 공급사와 다른 점
  - MOQ 필드명: buyCnt (구매 수량 단위)
  - AI 가중치: 공급사신뢰도(30%) + 출고속도(25%) + 품절률(25%) + 마진(20%)
  - 온채널 자체가 여러 공급사를 중개하므로, 공급사별 신뢰도 별도 추적 필요
  - 스크래핑 기반 (로그인 필요)
"""
from __future__ import annotations

import logging

from app.suppliers.base import BaseSupplierAdapter, NormalizedProduct
from app.config import get_settings

logger = logging.getLogger(__name__)


class OnchanelAdapter(BaseSupplierAdapter):
    supplier_id = "onchannel"
    display_name = "온채널"

    # ── AI 점수 가중치 ────────────────────────────────────────────────────────
    SCORE_WEIGHTS = {
        "supplier_reliability": 0.30,  # 공급사 신뢰도 (온채널 중간 공급사)
        "lead_time":            0.25,  # 출고 속도
        "stockout_rate":        0.25,  # 품절률 (낮을수록 좋음)
        "margin":               0.20,  # 마진율
    }

    def is_available(self) -> bool:
        s = get_settings()
        return bool(s.onchannel_login_id)

    def search(self, keyword: str, page: int = 1, limit: int = 50,
               min_price: int = 3000, moq: int = 1) -> list[NormalizedProduct]:
        try:
            from app.suppliers.onchannel import search as _raw_search
            raw_items = _raw_search(keyword=keyword, limit=limit)
        except Exception as exc:
            logger.warning("온채널 검색 실패 [%s]: %s", keyword, exc)
            return []

        results = []
        for item in raw_items:
            if item.supply_price < min_price:
                continue
            # 온채널 MOQ 필드: buyCnt → moq
            item_moq = getattr(item, "moq", 1)
            if item_moq > moq:
                continue

            # 온채널 특화: 품절률은 현재 데이터 없으면 카테고리 평균값 추정
            stockout_rate = _estimate_stockout_rate(item.category)

            results.append(NormalizedProduct(
                supplier_id=self.supplier_id,
                raw_id=item.source_id,
                raw_url=item.source_url,
                name=item.name,
                supply_price=item.supply_price,
                retail_price=getattr(item, "retail_price", item.supply_price * 2),
                moq=item_moq,
                stock=getattr(item, "stock", 0),
                shipping_fee=getattr(item, "shipping_fee", 3000.0),
                lead_time_days=getattr(item, "lead_time_days", 4),   # 온채널은 1단계 더 거침
                category=item.category,
                brand=item.brand,
                origin=item.origin,
                material=item.material,
                images=self._clean_images(item.images),
                detail_images=self._clean_images(item.detail_images),
                options=self._normalize_options(item.options),
                # 온채널 특화 지표
                supplier_reliability=_estimate_supplier_reliability(item.category),
                stockout_rate=stockout_rate,
                fulfillment_rate=0.88,      # 온채널은 중간상이라 다소 낮음
                avg_shipping_days=4.0,
                raw_data={
                    "source": "onchannel",
                    "source_id": item.source_id,
                    "original_name": item.name,
                    "buyCnt": item_moq,         # 원본 필드명 보존
                    "est_stockout_rate": stockout_rate,
                },
            ))

        return results

    def get_product(self, product_id: str) -> NormalizedProduct | None:
        try:
            from app.suppliers.onchannel import get_product
            item = get_product(product_id)
            if not item:
                return None

            moq = getattr(item, "moq", 1)
            stockout_rate = _estimate_stockout_rate(item.category)
            return NormalizedProduct(
                supplier_id=self.supplier_id,
                raw_id=item.source_id,
                raw_url=item.source_url,
                name=item.name,
                supply_price=item.supply_price,
                retail_price=getattr(item, "retail_price", item.supply_price * 2),
                moq=moq,
                stock=getattr(item, "stock", 0),
                shipping_fee=getattr(item, "shipping_fee", 3000.0),
                lead_time_days=4,
                category=item.category,
                brand=item.brand,
                origin=item.origin,
                material=item.material,
                images=self._clean_images(item.images),
                detail_images=self._clean_images(item.detail_images),
                options=self._normalize_options(item.options),
                supplier_reliability=_estimate_supplier_reliability(item.category),
                stockout_rate=stockout_rate,
                fulfillment_rate=0.88,
                avg_shipping_days=4.0,
                raw_data={"source": "onchannel", "buyCnt": moq,
                          "est_stockout_rate": stockout_rate},
            )
        except Exception as exc:
            logger.error("온채널 상세 조회 실패 [%s]: %s", product_id, exc)
            return None


# ── 온채널 전용 추정 함수 ──────────────────────────────────────────────────────
# 실제 품절 이력 데이터가 없으면 카테고리별 경험치 기반 추정

_STOCKOUT_BY_CATEGORY = {
    "패션": 0.20,  "의류": 0.20,  "신발": 0.18,
    "전자": 0.10,  "주방": 0.08,  "생활": 0.07,
    "뷰티": 0.12,  "식품": 0.05,  "완구": 0.15,
}

_RELIABILITY_BY_CATEGORY = {
    "전자": 0.85,  "주방": 0.90,  "생활": 0.88,
    "패션": 0.75,  "의류": 0.75,  "뷰티": 0.82,
    "식품": 0.92,  "완구": 0.78,
}


def _estimate_stockout_rate(category: str) -> float:
    for key, rate in _STOCKOUT_BY_CATEGORY.items():
        if key in (category or ""):
            return rate
    return 0.12  # 기본값


def _estimate_supplier_reliability(category: str) -> float:
    for key, rel in _RELIABILITY_BY_CATEGORY.items():
        if key in (category or ""):
            return rel
    return 0.80  # 기본값
