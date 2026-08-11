"""상세설명 SEO 재작성 — 플랫폼별 톤 차이를 반영한 재작성.

쿠팡은 상품명/카테고리/키워드 중심의 간결한 설명을,
네이버 스마트스토어는 자연스러운 문장형 설명을 선호한다는 사용자 요구를 반영해
플랫폼별로 다른 프롬프트를 사용한다. Claude 미설정/실패 시 원본 상세설명을
그대로 반환한다 (임의 생성보다 원본 유지가 안전).
"""
from __future__ import annotations
import json
import logging
import re

from app.config import get_settings
from app.db import Product, get_db

logger = logging.getLogger(__name__)

_PLATFORM_TONE = {
    "coupang": "핵심 키워드와 스펙을 간결하게 나열하는 톤 (쿠팡 검색 알고리즘은 키워드 밀도를 중시)",
    "smartstore": "자연스러운 문장형 설명 (네이버는 과도한 키워드 나열보다 읽기 쉬운 설명을 선호)",
}


def rewrite_detail_html(product_id: int, platform: str, keywords: list[str] | None = None) -> str:
    """상품 상세설명을 플랫폼에 맞게 재작성한다. 실패 시 원본 유지."""
    with get_db() as db:
        p = db.query(Product).filter_by(id=product_id).first()
        if not p:
            return ""
        name, category, material, origin = p.name, p.category, p.material, p.origin
        options = json.loads(p.options or "[]")
        original_html = p.detail_html or ""

    s = get_settings()
    if not s.claude_api_key:
        return original_html

    tone = _PLATFORM_TONE.get(platform, _PLATFORM_TONE["smartstore"])
    keyword_text = ", ".join((keywords or [])[:15])
    opt_lines = "\n".join(f"- {o['name']}: {', '.join(o['values'])}" for o in options)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=s.claude_api_key)
        msg = client.messages.create(
            model=s.claude_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": f"""
당신은 한국 이커머스 상세페이지 SEO 전문가입니다. 아래 상품의 상세설명 HTML을
{tone}으로 재작성하세요.

[상품 정보]
상품명: {name}
카테고리: {category}
소재: {material or "미상"}
원산지: {origin}
옵션:
{opt_lines or "  없음"}
주요 키워드(자연스럽게 녹여서 사용, 과도한 반복 금지): {keyword_text or "없음"}

[요구사항]
1. 상품 특징 3~5가지, 소재/사이즈/세탁법, 추천 대상, 배송 안내 포함
2. HTML 태그만 사용, 스크립트 금지, style은 font-family:sans-serif, max-width:860px
3. 허위·과장 표현 금지

JSON으로만 응답: {{"detail_html": "<div>...</div>"}}"""}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            html = data.get("detail_html", "")
            if html:
                return html
    except Exception as exc:
        err_str = str(exc)
        if "401" in err_str or "authentication_error" in err_str:
            logger.warning("Claude API 키 인증 실패 — 설정 > API 연동에서 claude_api_key를 확인하세요.")
        else:
            logger.warning("상세설명 재작성 실패 (원본 유지): %s", exc)

    return original_html
