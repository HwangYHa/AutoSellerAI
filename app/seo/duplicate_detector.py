"""유사 상품명 중복 탐지 — app/pipeline.py:_deduplicate_normalized()와 동일한
정규화 규칙(특수문자 제거 → 소문자 → 공백 정리 → 앞 30자 비교)을 재사용해
이미 등록된 상품끼리 이름이 사실상 같은지 판정한다.
"""
from __future__ import annotations
import re

from app.db import Product, get_db


def _normalize(name: str) -> str:
    name = re.sub(r"[^\w가-힣]", " ", name.lower())
    return " ".join(name.split())


def find_duplicates(product_id: int) -> list[dict]:
    """동일 상품군으로 판단되는 다른 상품 목록을 반환한다.

    Returns:
        [{"product_id": int, "name": str, "sell_price": float}]
    """
    with get_db() as db:
        target = db.query(Product).filter_by(id=product_id).first()
        if not target:
            return []
        target_key = _normalize(target.name)[:30]

        candidates = db.query(Product).filter(Product.id != product_id).all()
        return [
            {"product_id": c.id, "name": c.name, "sell_price": float(c.sell_price)}
            for c in candidates
            if _normalize(c.name)[:30] == target_key
        ]
