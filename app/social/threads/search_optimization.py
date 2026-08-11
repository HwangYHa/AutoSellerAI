from __future__ import annotations

import re
from typing import Any


def _clean_words(value: str) -> list[str]:
    text = re.sub(r"[^0-9A-Za-z가-힣 ]", " ", str(value or ""))
    return [w for w in text.split() if len(w) >= 2]


def build_search_context(product: dict[str, Any]) -> dict[str, Any]:
    """상품 데이터만 사용해 SEO/GEO/AEO용 검색·답변 컨텍스트를 만든다.

    외부 사실을 추측하지 않는다. 상품 DB에 실제 존재하는 값만 엔티티/근거로 사용한다.
    """
    name = str(product.get("name") or "상품").strip()
    category = str(product.get("category") or "").strip()
    brand = str(product.get("brand") or "").strip()
    origin = str(product.get("origin") or "").strip()
    material = str(product.get("material") or "").strip()

    candidates: list[str] = []
    for value in (name, category, brand):
        for word in _clean_words(value):
            if word not in candidates:
                candidates.append(word)

    primary_keyword = " ".join(_clean_words(name)[:3]) or category or "상품 정보"
    related_keywords = [w for w in candidates if w not in primary_keyword.split()][:8]

    entity_facts: list[str] = []
    if category:
        entity_facts.append(f"카테고리: {category}")
    if brand:
        entity_facts.append(f"브랜드: {brand}")
    if origin:
        entity_facts.append(f"원산지: {origin}")
    if material:
        entity_facts.append(f"소재: {material}")
    if product.get("sell_price") not in (None, "", 0, 0.0):
        try:
            entity_facts.append(f"판매가: {float(product['sell_price']):,.0f}원")
        except (TypeError, ValueError):
            pass

    faq_question = (
        f"{primary_keyword}을 고를 때 무엇을 확인해야 하나요?"
        if primary_keyword else "이 상품을 고를 때 무엇을 확인해야 하나요?"
    )

    return {
        "primary_keyword": primary_keyword,
        "related_keywords": related_keywords,
        "entity_name": name,
        "entity_facts": entity_facts,
        "faq_question": faq_question,
        "seo_rules": [
            "핵심 검색어를 첫 1~2문장 안에 자연스럽게 1회 사용",
            "관련 검색어는 문맥에 맞는 경우만 사용하고 키워드 나열 금지",
            "상품명·카테고리·브랜드를 검색 의도와 연결",
        ],
        "geo_rules": [
            "AI 검색엔진이 인용하기 쉬운 짧고 명확한 사실 문장 사용",
            "상품 DB에 존재하는 엔티티와 사실만 사용",
            "누가/무엇을/언제 써야 하는지 맥락을 명확히 표현",
        ],
        "aeo_rules": [
            "실제 구매자가 할 법한 질문을 포함",
            "질문 직후 핵심 답변을 먼저 제시",
            "FAQ처럼 짧고 독립적으로 이해 가능한 답변 문장 구성",
        ],
    }


def fallback_optimized_body(product: dict[str, Any], cta_keyword: str = "") -> tuple[str, dict[str, Any]]:
    ctx = build_search_context(product)
    name = ctx["entity_name"]
    primary = ctx["primary_keyword"]
    category = str(product.get("category") or "제품")
    keyword = cta_keyword.strip() or (_clean_words(name)[0] if _clean_words(name) else "정보")

    facts = ctx["entity_facts"][:2]
    fact_sentence = " · ".join(facts)
    body = (
        f"{primary} 찾고 계신가요? {category} 제품은 가격만 보기보다 실제 사용 목적과 옵션을 먼저 확인하는 게 좋습니다. "
        f"현재 확인 중인 상품은 ‘{name}’입니다."
    )
    if fact_sentence:
        body += f" 확인된 정보는 {fact_sentence}입니다."
    body += (
        f"\n\nQ. {ctx['faq_question']}\n"
        f"A. 사용 목적, 옵션·규격, 판매조건을 먼저 비교하세요. "
        f"상품 정보가 필요하면 ‘{keyword}’라고 댓글 남겨주세요."
    )
    return body[:500], ctx


def optimization_scores(body: str, ctx: dict[str, Any]) -> dict[str, float]:
    text = str(body or "")
    primary = str(ctx.get("primary_keyword") or "")
    related = ctx.get("related_keywords") or []
    facts = ctx.get("entity_facts") or []

    seo = 55.0
    if primary and primary in text[:180]:
        seo += 25
    seo += min(20, sum(1 for k in related if k and k in text) * 5)

    geo = 55.0
    if str(ctx.get("entity_name") or "") in text:
        geo += 20
    geo += min(25, sum(1 for f in facts if f.split(":", 1)[-1].strip() in text) * 8)

    aeo = 55.0
    if "Q." in text or "?" in text:
        aeo += 20
    if "A." in text or "답" in text:
        aeo += 20
    if "확인" in text or "먼저" in text:
        aeo += 5

    return {
        "seo_score": min(100.0, seo),
        "geo_score": min(100.0, geo),
        "aeo_score": min(100.0, aeo),
    }
