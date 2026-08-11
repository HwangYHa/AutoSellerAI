"""공급사 어댑터 공통 인터페이스 및 정규화 모델.

아키텍처 원칙:
  - 공급사 내부 구조(필드명·API 포맷)는 각 어댑터가 캡슐화
  - 플랫폼 코어는 NormalizedProduct만 사용
  - 새 공급사 추가 = 어댑터 파일 1개 + registry.py 등록만 필요

필드 정규화 예시:
  도매꾹  {"min_order_qty": 1}
  도매매  {"minimumQty": 1}
  온채널  {"buyCnt": 1}
  → NormalizedProduct.moq = 1
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# ── 통합 상품 모델 ──────────────────────────────────────────────────────────────

@dataclass
class NormalizedProduct:
    """공급사 원본 데이터를 플랫폼 공통 형식으로 정규화한 상품."""

    # ── 공급사 식별 ──────────────────────────────────────────────────────────
    supplier_id: str = ""        # "domeggook" | "domemai" | "onchannel"
    raw_id: str = ""             # 공급사 원본 상품 ID
    raw_url: str = ""            # 공급사 상품 페이지 URL

    # ── 상품 기본 정보 ────────────────────────────────────────────────────────
    name: str = ""
    supply_price: float = 0.0    # 공급가 (원가)
    retail_price: float = 0.0    # 소비자가 (참고용)
    moq: int = 1                 # 최소주문수량 (통합 필드)
    stock: int = 0               # 재고 수량 (0 = 무한재고 가능)
    shipping_fee: float = 3000.0 # 배송비
    lead_time_days: int = 3      # 출고 소요일 (영업일 기준)

    category: str = ""
    brand: str = ""
    origin: str = "중국"
    material: str = ""
    tags: list[str] = field(default_factory=list)

    images: list[str] = field(default_factory=list)
    detail_images: list[str] = field(default_factory=list)
    options: list[dict] = field(default_factory=list)
    # options: [{"name": "색상", "values": ["빨강", "파랑"]}]

    # ── 공급사별 신뢰도 지표 ──────────────────────────────────────────────────
    # 각 어댑터가 계산해 채워줌; AI 점수 엔진이 가중치 적용
    supplier_reliability: float = 1.0   # 공급사 신뢰도 0.0~1.0 (온채널 전용)
    stockout_rate: float = 0.0          # 품절 비율 0.0~1.0 (온채널 전용)
    fulfillment_rate: float = 1.0       # 발주 성공률 0.0~1.0 (도매매 전용)
    avg_shipping_days: float = 3.0      # 평균 실제 출고일 (도매꾹/도매매)

    # ── 원본 JSON ─────────────────────────────────────────────────────────────
    raw_data: dict = field(default_factory=dict)

    def as_import_dict(self) -> dict:
        """pipeline.import_product 호환 dict 반환."""
        return {
            "source": self.supplier_id,
            "source_id": self.raw_id,
            "source_url": self.raw_url,
            "name": self.name,
            "supply_price": self.supply_price,
            "category": self.category,
            "brand": self.brand,
            "origin": self.origin,
            "material": self.material,
            "images": self.images,
            "detail_images": self.detail_images,
            "options": self.options,
            "moq": self.moq,
            "stock": self.stock,
            "shipping_fee": self.shipping_fee,
            "lead_time_days": self.lead_time_days,
        }

    def raw_json(self) -> str:
        return json.dumps(self.raw_data, ensure_ascii=False)


# ── 어댑터 프로토콜 ─────────────────────────────────────────────────────────────

@runtime_checkable
class SupplierAdapter(Protocol):
    """공급사 어댑터가 반드시 구현해야 하는 인터페이스."""

    supplier_id: str
    display_name: str

    def search(
        self,
        keyword: str,
        page: int = 1,
        limit: int = 50,
        min_price: int = 3000,
        moq: int = 1,
    ) -> list[NormalizedProduct]:
        """키워드로 상품을 검색하고 NormalizedProduct 목록을 반환한다."""
        ...

    def get_product(self, product_id: str) -> NormalizedProduct | None:
        """단건 상품 상세를 조회한다."""
        ...

    def is_available(self) -> bool:
        """API 키·자격증명이 설정되어 있으면 True."""
        ...


# ── 어댑터 베이스 클래스 (선택적 상속) ─────────────────────────────────────────

class BaseSupplierAdapter:
    """공통 유틸리티를 제공하는 어댑터 베이스. 상속 필수 아님."""

    supplier_id: str = ""
    display_name: str = ""

    def is_available(self) -> bool:
        return False

    def search(self, keyword: str, page: int = 1, limit: int = 50,
               min_price: int = 3000, moq: int = 1) -> list[NormalizedProduct]:
        return []

    def get_product(self, product_id: str) -> NormalizedProduct | None:
        return None

    @staticmethod
    def _clean_images(urls: list, base_url: str = "") -> list[str]:
        result = []
        for u in urls:
            if not u:
                continue
            u = str(u).strip()
            if u.startswith("//"):
                u = "https:" + u
            elif u.startswith("/") and base_url:
                u = base_url.rstrip("/") + u
            if u.startswith("http"):
                result.append(u)
        return result

    @staticmethod
    def _parse_price(val) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        import re
        nums = re.findall(r"[\d,]+", str(val))
        return float(nums[0].replace(",", "")) if nums else 0.0

    @staticmethod
    def _normalize_options(raw_options) -> list[dict]:
        """다양한 공급사 옵션 포맷을 통일된 형식으로 변환.

        입력 예:
          도매꾹: [{"optionName": "색상", "values": ["빨강"]}]
          도매매: [{"name": "사이즈", "items": ["S", "M"]}]
          온채널: 직접 파싱
        출력: [{"name": "색상", "values": ["빨강"]}]
        """
        if not raw_options or not isinstance(raw_options, list):
            return []
        result = []
        for opt in raw_options:
            if not isinstance(opt, dict):
                continue
            name = (opt.get("name") or opt.get("optionName")
                    or opt.get("optionGroupName") or "옵션")
            values = (opt.get("values") or opt.get("items")
                      or opt.get("optionValues") or [])
            if isinstance(values, str):
                values = [v.strip() for v in values.split(",") if v.strip()]
            if values:
                result.append({"name": str(name), "values": [str(v) for v in values]})
        return result
