"""도매매 공급사 어댑터 (Layer 1).

[도매매 특성]
  - 직거래 구조: 도매매 → 판매자
  - MOQ 필드명: minimumQty
  - AI 가중치: 재고안정성(35%) + 발주성공률(30%) + 마진(35%)
  - REST API v1 (api_key 인증)
"""
from __future__ import annotations

import logging

from app.suppliers.base import BaseSupplierAdapter, NormalizedProduct
from app.config import get_settings

logger = logging.getLogger(__name__)


class DomemaiAdapter(BaseSupplierAdapter):
    supplier_id = "domemai"
    display_name = "도매매"

    # ── AI 점수 가중치 ────────────────────────────────────────────────────────
    SCORE_WEIGHTS = {
        "stock_stability":   0.35,  # 재고 안정성 (수량·변동성)
        "fulfillment_rate":  0.30,  # 발주 성공률
        "margin":            0.35,  # 마진율
    }

    def is_available(self) -> bool:
        s = get_settings()
        return bool(s.domemai_api_key or s.domeggook_api_key)

    def search(self, keyword: str, page: int = 1, limit: int = 50,
               min_price: int = 3000, moq: int = 1) -> list[NormalizedProduct]:
        try:
            from app.suppliers.domemai import search as _raw_search
            raw_items = _raw_search(keyword=keyword, page=page, limit=limit,
                                     min_price=min_price, moq=moq)
        except Exception as exc:
            logger.warning("도매매 검색 실패 [%s]: %s", keyword, exc)
            return []

        results = []
        for item in raw_items:
            # 도매매 원본 필드: minimumQty → moq
            item_moq = getattr(item, "moq", 1)
            stock = getattr(item, "stock", 0)

            # 재고 안정성 지표: 50개 이상이면 high
            stock_stability = min(1.0, (stock / 100)) if stock > 0 else 0.8

            results.append(NormalizedProduct(
                supplier_id=self.supplier_id,
                raw_id=item.source_id,
                raw_url=item.source_url,
                name=item.name,
                supply_price=item.supply_price,
                retail_price=getattr(item, "retail_price", item.supply_price * 2),
                moq=item_moq,
                stock=stock,
                shipping_fee=getattr(item, "shipping_fee", 3000.0),
                lead_time_days=getattr(item, "lead_time_days", 2),
                category=item.category,
                brand=item.brand,
                origin=item.origin,
                material=item.material,
                images=self._clean_images(item.images),
                detail_images=self._clean_images(item.detail_images),
                options=self._normalize_options(item.options),
                # 도매매 특화 지표
                fulfillment_rate=0.92,          # 기본값; 실적 데이터 연동 시 갱신
                avg_shipping_days=2.0,          # 도매매는 평균 빠름
                supplier_reliability=stock_stability,
                raw_data={
                    "source": "domemai",
                    "source_id": item.source_id,
                    "original_name": item.name,
                    "minimumQty": item_moq,     # 원본 필드명 보존
                    "stock": stock,
                },
            ))

        return results

    def get_product(self, product_id: str) -> NormalizedProduct | None:
        try:
            from app.suppliers.domemai import get_product as _raw_get
            item = _raw_get(product_id)
            if not item:
                return None

            moq = getattr(item, "moq", 1)
            stock = getattr(item, "stock", 0)
            return NormalizedProduct(
                supplier_id=self.supplier_id,
                raw_id=item.source_id,
                raw_url=item.source_url,
                name=item.name,
                supply_price=item.supply_price,
                retail_price=getattr(item, "retail_price", item.supply_price * 2),
                moq=moq,
                stock=stock,
                shipping_fee=getattr(item, "shipping_fee", 3000.0),
                lead_time_days=2,
                category=item.category,
                brand=item.brand,
                origin=item.origin,
                material=item.material,
                images=self._clean_images(item.images),
                detail_images=self._clean_images(item.detail_images),
                options=self._normalize_options(item.options),
                fulfillment_rate=0.92,
                avg_shipping_days=2.0,
                raw_data={"source": "domemai", "minimumQty": moq, "stock": stock},
            )
        except Exception as exc:
            logger.error("도매매 상세 조회 실패 [%s]: %s", product_id, exc)
            return None
