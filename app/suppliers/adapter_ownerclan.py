"""오너클랜 판매사 API 공급처 어댑터.

현재 공식 문서로 확인 가능한 단일 상품 조회(item key)를 우선 안정 지원한다.
검색창에 오너클랜 상품코드(W000000 등)를 입력하면 직접 조회한다.
광범위 키워드 목록 검색은 오너클랜 GraphQL 스키마를 실제 계정으로 확인한 뒤 확장한다.
"""
from __future__ import annotations

import logging
import re

from app.config import get_settings
from app.suppliers.base import BaseSupplierAdapter, NormalizedProduct
from app.suppliers.ownerclan import get_ownerclan_client

logger = logging.getLogger(__name__)

_OWNERCLAN_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{4,}$")


class OwnerClanAdapter(BaseSupplierAdapter):
    supplier_id = "ownerclan"
    display_name = "오너클랜"

    def is_available(self) -> bool:
        s = get_settings()
        return bool((s.ownerclan_username or "").strip() and (s.ownerclan_password or "").strip())

    def search(self, keyword: str, page: int = 1, limit: int = 50,
               min_price: int = 3000, moq: int = 1) -> list[NormalizedProduct]:
        """상품코드 직접 조회를 지원한다.

        오너클랜의 복수상품 검색 필드/검색 인자는 계정별 API 스키마 확인 전에는
        추측해서 호출하지 않는다. 상품코드 기반 조회는 공식 문서의 item(key:)를 사용한다.
        """
        key = (keyword or "").strip()
        if not key or not _OWNERCLAN_KEY.match(key):
            return []
        product = self.get_product(key)
        if not product:
            return []
        if product.supply_price < min_price or product.moq > moq:
            return []
        return [product]

    def get_product(self, product_id: str) -> NormalizedProduct | None:
        try:
            raw = get_ownerclan_client().get_item(str(product_id).strip())
            if not raw:
                return None
            return self._normalize(raw)
        except Exception as exc:
            logger.warning("오너클랜 상품 조회 실패 [%s]: %s", product_id, exc)
            return None

    def _normalize(self, raw: dict) -> NormalizedProduct:
        options_raw = raw.get("options") or []
        prices: list[float] = []
        stocks: list[int] = []
        grouped: dict[str, list[str]] = {}

        for option in options_raw:
            try:
                price = float(option.get("price") or 0)
            except (TypeError, ValueError):
                price = 0.0
            if price > 0:
                prices.append(price)
            try:
                stocks.append(max(0, int(option.get("quantity") or 0)))
            except (TypeError, ValueError):
                pass
            for attr in option.get("optionAttributes") or []:
                name = str(attr.get("name") or "옵션").strip()
                value = str(attr.get("value") or "").strip()
                if value and value not in grouped.setdefault(name, []):
                    grouped[name].append(value)

        supply_price = min(prices) if prices else 0.0
        options = [{"name": name, "values": values} for name, values in grouped.items() if values]
        key = str(raw.get("key") or "").strip()
        name = str(raw.get("name") or raw.get("model") or key).strip()

        return NormalizedProduct(
            supplier_id=self.supplier_id,
            raw_id=key,
            raw_url=f"https://ownerclan.com/V2/product/view.php?itemCode={key}" if key else "",
            name=name,
            supply_price=supply_price,
            retail_price=supply_price,
            moq=1,
            stock=sum(stocks) if stocks else 0,
            shipping_fee=3000.0,
            lead_time_days=3,
            category="",
            brand="",
            origin="",
            material="",
            images=[],
            detail_images=[],
            options=options,
            supplier_reliability=0.90,
            fulfillment_rate=0.90,
            avg_shipping_days=3.0,
            raw_data=raw,
        )
