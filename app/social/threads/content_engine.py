from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings
from app.social.threads.search_optimization import (
    build_search_context,
    fallback_optimized_body,
    optimization_scores,
)


ANGLES = {
    "problem_solution": "문제 해결형",
    "experience": "경험/공감형",
    "question": "질문형",
    "comparison": "비교형",
    "listicle": "리스트형",
}


def generate_threads_content(product: dict[str, Any], angle: str = "problem_solution",
                             cta_keyword: str = "", count: int = 3,
                             performance_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if performance_context is None and product.get("id"):
        try:
            from app.social.threads.profit_feedback import learning_context
            performance_context = learning_context(int(product["id"]))
        except Exception:
            performance_context = {}
    performance_context = performance_context or {}
    preferred = [x for x in performance_context.get("preferred_angles", []) if x in ANGLES]
    avoid = [x for x in performance_context.get("avoid_angles", []) if x in ANGLES]

    if angle not in ANGLES:
        angle = preferred[0] if preferred else "problem_solution"
    elif angle == "problem_solution" and preferred and performance_context.get("sample_orders", 0) >= 3:
        angle = preferred[0]
    if angle in avoid and preferred:
        angle = preferred[0]

    count = max(1, min(int(count), 5))
    settings = get_settings()
    search_ctx = build_search_context(product)

    feedback_text = "실적 데이터 없음"
    if performance_context:
        feedback_text = json.dumps({
            "선호 콘텐츠 각도": [ANGLES.get(x, x) for x in preferred],
            "피해야 할 각도": [ANGLES.get(x, x) for x in avoid],
            "성과 상위 패턴": performance_context.get("winning_patterns", [])[:5],
            "학습 게시물 수": performance_context.get("sample_posts", 0),
            "귀속 주문 수": performance_context.get("sample_orders", 0),
            "누적 순이익": performance_context.get("total_net_profit", 0),
            "평균 Content Score": performance_context.get("avg_content_score", 0),
        }, ensure_ascii=False)

    if settings.claude_api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.claude_api_key)
            prompt = f"""당신은 한국 이커머스 Threads 광고 콘텐츠 에디터입니다.
목표는 조회수 최대화가 아니라 **실제 귀속 순이익 최대화 + SEO/GEO/AEO 동시 최적화**입니다.
광고문구처럼 밀어붙이지 말고 정보/공감형 콘텐츠를 작성하세요.
상품 DB에 없는 성능, 인증, 배송일, 할인율, 최저가를 추측하거나 만들지 마세요.
본문은 500자 이하, 과장표현·허위후기·가짜 사용경험 금지입니다.

[SEO]
- 핵심 검색어를 첫 1~2문장 안에 자연스럽게 사용합니다.
- 키워드 나열 대신 검색 의도에 맞는 문장을 만듭니다.
- 상품명·카테고리·브랜드를 검색 가능한 표현으로 연결합니다.

[GEO]
- ChatGPT/Gemini/Perplexity 같은 AI가 인용·추천하기 쉬운 명확한 사실 문장을 포함합니다.
- 상품 DB에 존재하는 엔티티와 사실만 사용합니다.
- 무엇인지, 누구에게 필요한지, 무엇을 비교해야 하는지 한 문장씩 명확히 씁니다.

[AEO]
- 실제 구매자가 검색/질문할 법한 질문을 최소 1개 포함합니다.
- 질문 직후 핵심 답변을 먼저 제시합니다.
- FAQ처럼 독립적으로 이해 가능한 짧은 답변 구조를 사용합니다.

상품정보(JSON): {json.dumps(product, ensure_ascii=False)}
검색최적화 컨텍스트(JSON): {json.dumps(search_ctx, ensure_ascii=False)}
수익성 피드백(JSON): {feedback_text}
콘텐츠 각도: {ANGLES[angle]}
CTA 키워드: {cta_keyword or '상품명에서 자연스럽게 1개 생성'}
후보 수: {count}

수익성 피드백에 충분한 주문 표본이 있으면 순이익과 Content Score가 높은 패턴을 우선하고,
순이익이 음수이거나 반품률이 높은 패턴은 모방하지 마세요. 표본이 적으면 과적합하지 마세요.

JSON 배열만 반환하세요.
각 항목: {{"body":"...","cta_keyword":"...","score":0~100,"reason":"..."}}
"""
            msg = client.messages.create(
                model=settings.claude_model,
                max_tokens=2200,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                rows = json.loads(match.group())
                result = []
                for row in rows[:count]:
                    body = str(row.get("body", "")).strip()[:500]
                    if not body:
                        continue
                    keyword = str(row.get("cta_keyword", cta_keyword)).strip()[:100]
                    score = float(row.get("score", 70))
                    search_scores = optimization_scores(body, search_ctx)
                    result.append({
                        "body": body,
                        "cta_keyword": keyword,
                        "score": max(0.0, min(score, 100.0)),
                        "reason": str(row.get("reason", "AI 생성"))[:240],
                        "source": "ai_profit_feedback" if performance_context else "ai",
                        "selected_angle": angle,
                        "primary_keyword": search_ctx["primary_keyword"],
                        "related_keywords": search_ctx["related_keywords"],
                        "faq_question": search_ctx["faq_question"],
                        **search_scores,
                    })
                if result:
                    return result
        except Exception:
            pass

    return _fallback_variants(product, angle, cta_keyword, count, bool(performance_context))


def _fallback_variants(product: dict[str, Any], angle: str, cta_keyword: str, count: int,
                       feedback_used: bool = False) -> list[dict[str, Any]]:
    base_body, search_ctx = fallback_optimized_body(product, cta_keyword)
    keyword = cta_keyword.strip() or _keyword_from_name(str(product.get("name") or "이 상품"))
    name = str(product.get("name") or "이 상품")
    category = str(product.get("category") or "제품")

    angle_prefix = {
        "problem_solution": f"{category} 제품을 고를 때 가장 먼저 해결해야 할 건 ‘내 사용 목적에 맞는가’입니다. ",
        "experience": f"{category} 제품을 비교할 때 광고 문구보다 실제 확인 가능한 정보를 먼저 보게 됩니다. ",
        "question": f"{category} 제품, 무엇을 기준으로 고르시나요? ",
        "comparison": f"가격만 낮은 제품과 용도에 맞는 제품 중 무엇이 더 중요한지 비교해보세요. ",
        "listicle": f"{category} 구매 전 체크 3가지: 사용 목적, 옵션·규격, 최종 판매조건. ",
    }.get(angle, "")

    result = []
    for i in range(count):
        body = (angle_prefix + base_body)[:500] if i == 0 else base_body[:500]
        search_scores = optimization_scores(body, search_ctx)
        result.append({
            "body": body,
            "cta_keyword": keyword,
            "score": 70.0 if feedback_used else 67.0,
            "reason": "순이익 전략 + SEO/GEO/AEO 안전 초안" if feedback_used else "SEO/GEO/AEO 규칙 기반 안전 초안",
            "source": "rule_profit_feedback" if feedback_used else "rule",
            "selected_angle": angle,
            "primary_keyword": search_ctx["primary_keyword"],
            "related_keywords": search_ctx["related_keywords"],
            "faq_question": search_ctx["faq_question"],
            **search_scores,
        })
    return result


def _keyword_from_name(name: str) -> str:
    words = re.sub(r"[^0-9A-Za-z가-힣 ]", " ", name).split()
    return (words[0] if words else "정보")[:20]
