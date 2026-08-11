"""상품명 A/B 후보 생성 — app/ai.py:optimize_product()와 동일한 Claude 호출 컨벤션.

optimize_product()은 신규 등록 시 상품명 1개만 만든다. 이 모듈은 기존 등록
상품을 대상으로 검색 노출에 최적화된 후보 제목을 여러 개(기본 8개) 생성해
사람이 비교·검수할 수 있게 한다.
"""
from __future__ import annotations
import json
import logging
import re

from app.config import get_settings
from app.db import Product, get_db

logger = logging.getLogger(__name__)

# 쿠팡/스마트스토어 공통 금지어 (과장·불법 표현)
_BANNED_WORDS = ["최저가", "특가", "무료배송", "1위", "공식", "정품인증"]


def generate_title_candidates(product_id: int, count: int | None = None) -> list[str]:
    """검색 최적화된 상품명 후보를 생성한다 (원본 포함하지 않음)."""
    s = get_settings()
    count = count or s.seo_title_candidates

    with get_db() as db:
        p = db.query(Product).filter_by(id=product_id).first()
        if not p:
            return []
        name, category, brand, origin = p.name, p.category, p.brand, p.origin
        options = json.loads(p.options or "[]")

    if not s.claude_api_key:
        return [name]

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=s.claude_api_key)
        options_text = "\n".join(f"- {o['name']}: {', '.join(o['values'])}" for o in options)
        msg = client.messages.create(
            model=s.claude_model,
            max_tokens=1200,
            messages=[{"role": "user", "content": f"""
한국 이커머스 SEO 전문가입니다. 아래 상품의 검색 노출/클릭률을 높일 상품명 후보를
{count}개 생성하세요.

[요구사항]
- 각 후보는 50자 이내, 자연스러운 한국어 어순
- 핵심 키워드를 앞쪽에 배치
- 다음 금지어 절대 포함 금지: {', '.join(_BANNED_WORDS)}
- 후보끼리 표현 방식을 다양하게 (핵심키워드 조합/타겟층 강조/사용처 강조 등)

[상품 정보]
원본명: {name}
카테고리: {category}
브랜드: {brand or "없음"}
원산지: {origin}
옵션:
{options_text or "  없음"}

JSON으로만 응답: {{"titles": ["후보1", "후보2", ...]}}"""}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            titles = [t[:100] for t in data.get("titles", []) if t and not _contains_banned(t)]
            if titles:
                return titles[:count]
    except Exception as exc:
        err_str = str(exc)
        if "401" in err_str or "authentication_error" in err_str:
            logger.warning("Claude API 키 인증 실패 — 설정 > API 연동에서 claude_api_key를 확인하세요.")
        else:
            logger.warning("상품명 후보 생성 실패 (원본 유지): %s", exc)

    return [name]


def _contains_banned(title: str) -> bool:
    return any(w in title for w in _BANNED_WORDS)
