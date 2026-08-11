"""도매꾹 공급사 어댑터 (Layer 1).

[도매꾹 특성]
  - 직거래 구조: 도매꾹 → 판매자
  - MOQ 필드명: min_order_qty
  - AI 가중치: MOQ(30%) + 배송비(20%) + 마진(50%)
  - 세션 기반 API v4.0 (sId 필요)
"""
from __future__ import annotations

import logging

from app.suppliers.base import BaseSupplierAdapter, NormalizedProduct
from app.config import get_settings

logger = logging.getLogger(__name__)


class DomeggookAdapter(BaseSupplierAdapter):
    supplier_id = "domeggook"
    display_name = "도매꾹"

    # ── AI 점수 가중치 (공급사 특화) ──────────────────────────────────────────
    SCORE_WEIGHTS = {
        "moq":          0.30,   # MOQ=1 여부가 핵심 (도매꾹은 1개 안 파는 상품 많음)
        "shipping_fee": 0.20,   # 배송비 경쟁력
        "margin":       0.50,   # 마진율
    }

    def is_available(self) -> bool:
        s = get_settings()
        return bool(s.domeggook_api_key)

    def search(self, keyword: str, page: int = 1, limit: int = 50,
               min_price: int = 3000, moq: int = 1) -> list[NormalizedProduct]:
        try:
            from app.suppliers.domeggook import search as _raw_search
            raw_items = _raw_search(keyword=keyword, limit=limit)
        except Exception as exc:
            logger.warning("도매꾹 검색 실패 [%s]: %s", keyword, exc)
            return []

        results = []
        for item in raw_items:
            if item.supply_price < min_price:
                continue
            # 도매꾹 필드명 정규화
            item_moq = getattr(item, "moq", 1)
            if item_moq > moq:
                continue

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
                lead_time_days=getattr(item, "lead_time_days", 3),
                category=item.category,
                brand=item.brand,
                origin=item.origin,
                material=item.material,
                images=self._clean_images(item.images),
                detail_images=self._clean_images(item.detail_images),
                options=self._normalize_options(item.options),
                # 도매꾹 특화 지표
                avg_shipping_days=3.0,
                fulfillment_rate=0.95,
                raw_data={
                    "source": "domeggook",
                    "source_id": item.source_id,
                    "original_name": item.name,
                    "min_order_qty": item_moq,   # 원본 필드명 보존
                },
            ))

        return results

    def get_product(self, product_id: str) -> NormalizedProduct | None:
        try:
            from app.suppliers.domeggook import get_product as _raw_get
            item = _raw_get(product_id)
            if not item:
                return None

            moq = getattr(item, "moq", 1)
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
                lead_time_days=getattr(item, "lead_time_days", 3),
                category=item.category,
                brand=item.brand,
                origin=item.origin,
                material=item.material,
                images=self._clean_images(item.images),
                detail_images=self._clean_images(item.detail_images),
                options=self._normalize_options(item.options),
                avg_shipping_days=3.0,
                fulfillment_rate=0.95,
                raw_data={"source": "domeggook", "min_order_qty": moq},
            )
        except Exception as exc:
            logger.error("도매꾹 상세 조회 실패 [%s]: %s", product_id, exc)
            return None
