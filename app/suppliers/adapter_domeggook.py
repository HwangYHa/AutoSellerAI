"""도매꾹 공급사 어댑터.

상품조회는 공식 Open API를 사용한다.
- 목록: getItemList v4.1
- 상세: getItemView v4.6
구매/주문 기능은 별도 Private API 권한이 필요한 영역으로 분리한다.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.suppliers.base import BaseSupplierAdapter, NormalizedProduct
from app.suppliers.domeggook_openapi import get_product as _get_product
from app.suppliers.domeggook_openapi import search_products

logger = logging.getLogger(__name__)


class DomeggookAdapter(BaseSupplierAdapter):
    supplier_id = "domeggook"
    display_name = "도매꾹"

    SCORE_WEIGHTS = {
        "moq": 0.30,
        "shipping_fee": 0.20,
        "margin": 0.50,
    }

    def is_available(self) -> bool:
        return bool((get_settings().domeggook_api_key or "").strip())

    def search(
        self,
        keyword: str,
        page: int = 1,
        limit: int = 50,
        min_price: int = 3000,
        moq: int = 1,
    ) -> list[NormalizedProduct]:
        try:
            return search_products(
                keyword,
                page=page,
                limit=limit,
                min_price=min_price,
                max_moq=moq,
            )
        except Exception as exc:
            logger.warning("도매꾹 공식 API 검색 실패 [%s]: %s", keyword, exc)
            return []

    def get_product(self, product_id: str) -> NormalizedProduct | None:
        try:
            return _get_product(product_id)
        except Exception as exc:
            logger.error("도매꾹 공식 API 상세 조회 실패 [%s]: %s", product_id, exc)
            return None
