"""Claude AI — 상품명 최적화 + 상세 HTML 생성."""
from __future__ import annotations
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)


def optimize_product(name: str, category: str, options: list[dict],
                     origin: str = "중국", material: str = "") -> dict:
    """Claude로 상품명 최적화 + 상세 HTML 생성.

    Returns:
        {"name": str, "detail_html": str}
    """
    s = get_settings()
    if not s.claude_api_key:
        return {"name": name, "detail_html": _basic_html(name, category, options, origin, material)}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=s.claude_api_key)
        options_text = "\n".join(f"- {o['name']}: {', '.join(o['values'])}" for o in options)

        prompt = f"""당신은 한국 이커머스 상품 등록 전문가입니다.
아래 상품 정보로 쿠팡/스마트스토어에 최적화된 상품명과 상세 HTML을 생성하세요.

[상품 정보]
- 원본명: {name}
- 카테고리: {category}
- 원산지: {origin}
- 소재: {material or '미상'}
- 옵션:
{options_text or '  없음'}

[요구사항]
1. 상품명: 검색 최적화, 50자 이내, 금지어(특가/최저가/무료배송) 제외
2. 상세 HTML: 상품 특징 3~5가지, 소재/사이즈/세탁법, 배송 안내 포함
   - HTML 태그만 사용, 스크립트 금지
   - 스타일: font-family:sans-serif, max-width:860px

JSON으로만 응답하세요:
{{"name": "최적화된 상품명", "detail_html": "<div>...</div>"}}"""

        msg = client.messages.create(
            model=s.claude_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        import json, re
        text = msg.content[0].text.strip()
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return {
                "name": data.get("name", name)[:100],
                "detail_html": data.get("detail_html", _basic_html(name, category, options, origin, material)),
            }
    except Exception as e:
        err_str = str(e)
        if "401" in err_str or "authentication_error" in err_str or "invalid x-api-key" in err_str:
            logger.warning("Claude API 키 인증 실패 — 설정 > API 연동에서 claude_api_key를 확인하세요.")
        else:
            logger.warning("Claude AI 실패 (기본값 사용): %s", e)

    return {"name": name, "detail_html": _basic_html(name, category, options, origin, material)}


def _basic_html(name: str, category: str, options: list[dict],
                origin: str, material: str) -> str:
    opt_lines = "".join(
        f"<li><strong>{o['name']}</strong>: {', '.join(o['values'])}</li>"
        for o in options
    )
    return f"""<div style="font-family:sans-serif;max-width:860px;margin:0 auto;padding:20px;color:#333">
<h2 style="font-size:22px;border-bottom:2px solid #333;padding-bottom:10px">{name}</h2>
<h3 style="color:#555;margin-top:20px">상품 정보</h3>
<ul style="line-height:2">
  <li><strong>카테고리</strong>: {category}</li>
  {"<li><strong>소재</strong>: " + material + "</li>" if material else ""}
  <li><strong>원산지</strong>: {origin}</li>
  {opt_lines}
</ul>
<h3 style="color:#555;margin-top:20px">배송 안내</h3>
<ul style="line-height:2">
  <li>주문 확인 후 1~3일 이내 발송</li>
  <li>배송사 사정에 따라 지연될 수 있습니다</li>
</ul>
</div>"""
