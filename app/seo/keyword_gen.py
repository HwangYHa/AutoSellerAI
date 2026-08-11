"""검색 키워드/태그 생성 — 기존 app/pipeline.py:generate_product_keywords()의 확장판.

기존 함수는 키워드 10개만 생성하고 DB에 저장하지 않는다. 이 모듈은 최소
`seo_min_keywords`(기본 30)개 이상을 생성하고 중복을 제거해 SeoRevision에
저장할 수 있는 형태로 반환한다. Claude 미설정 시에는 상품명/카테고리/브랜드
토큰 조합으로 규칙 기반 폴백을 사용한다 (app/ai.py의 폴백 컨벤션과 동일).
"""
from __future__ import annotations
import json
import logging
import re

from app.config import get_settings
from app.db import Product, get_db

logger = logging.getLogger(__name__)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result


def _fallback_keywords(name: str, category: str, brand: str) -> dict:
    tokens = [t for t in re.sub(r"[^\w가-힣]", " ", name).split() if len(t) >= 2]
    base = _dedupe(tokens + [category, brand] + [f"{category} {t}" for t in tokens])
    return {"keywords": base, "tags": _dedupe([category, brand] + tokens[:5])}


def generate_keywords(product_id: int, min_count: int | None = None) -> dict:
    """상품에 대한 검색 키워드/태그를 생성한다.

    Returns:
        {"keywords": [str], "tags": [str]}
    """
    s = get_settings()
    min_count = min_count or s.seo_min_keywords

    with get_db() as db:
        p = db.query(Product).filter_by(id=product_id).first()
        if not p:
            return {"keywords": [], "tags": []}
        name, category, brand, origin = p.name, p.category, p.brand, p.origin

    if not s.claude_api_key:
        return _fallback_keywords(name, category, brand)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=s.claude_api_key)
        msg = client.messages.create(
            model=s.claude_model,
            max_tokens=1200,
            messages=[{"role": "user", "content": f"""
한국 이커머스 SEO 전문가입니다. 아래 상품에 대해 쿠팡/스마트스토어 검색 노출에
도움이 되는 검색 키워드 {min_count}개 이상과 태그 5개를 생성하세요.
- 실제 구매자가 검색할 법한 표현 위주 (롱테일 키워드 포함)
- 상품과 무관한 키워드나 과장 표현 금지
- 중복되거나 의미가 겹치는 키워드는 하나로 통일

상품명: {name}
카테고리: {category}
브랜드: {brand or "없음"}
원산지: {origin}

JSON으로만 응답: {{"keywords":["키워드1","키워드2"...],"tags":["태그1"...]}}"""}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            keywords = _dedupe(data.get("keywords", []))
            tags = _dedupe(data.get("tags", []))[:5]
            if len(keywords) < min_count:
                keywords = _dedupe(keywords + _fallback_keywords(name, category, brand)["keywords"])
            return {"keywords": keywords, "tags": tags}
    except Exception as exc:
        err_str = str(exc)
        if "401" in err_str or "authentication_error" in err_str:
            logger.warning("Claude API 키 인증 실패 — 설정 > API 연동에서 claude_api_key를 확인하세요.")
        else:
            logger.warning("키워드 생성 실패 (규칙 기반 폴백 사용): %s", exc)

    return _fallback_keywords(name, category, brand)
