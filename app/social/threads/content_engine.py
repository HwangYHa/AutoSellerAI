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

_FEATURE_MARKERS = (
    "무선", "휴대용", "충전식", "대용량", "초경량", "경량", "미니", "슬림",
    "접이식", "자동", "저소음", "방수", "세척", "멀티", "올인원", "고속",
    "강력", "컴팩트", "프리미엄", "실리콘", "스테인리스", "ABS",
)

_HOOK_SUFFIXES = ("찐포인트", "왜핫해", "궁금해", "비교해줘", "실사용팁")


def _clean_tokens(text: str) -> list[str]:
    return [x for x in re.sub(r"[^0-9A-Za-z가-힣 ]", " ", text or "").split() if len(x) >= 2]


def suggest_comment_keyword(product: dict[str, Any]) -> str:
    """상품의 확인 가능한 특징만 이용해 댓글 CTA용 짧은 후킹 키워드를 만든다.

    허위 할인/성능/후기처럼 DB에 없는 사실은 만들지 않는다. 사용자가 댓글로
    입력하기 쉬운 4~16자 수준의 키워드를 우선한다.
    """
    name = str(product.get("name") or "")
    category = str(product.get("category") or "")
    brand = str(product.get("brand") or "")
    material = str(product.get("material") or "")
    source = " ".join([name, category, brand, material])

    feature = next((marker for marker in _FEATURE_MARKERS if marker.lower() in source.lower()), "")
    if not feature:
        search_ctx = build_search_context(product)
        candidates = list(search_ctx.get("related_keywords") or [])
        candidates += _clean_tokens(name)
        candidates += _clean_tokens(category)
        feature = next((str(x).strip() for x in candidates if str(x).strip()), "상품")

    # 같은 상품은 항상 같은 추천이 나오도록 문자열 합으로 suffix를 결정한다.
    seed = sum(ord(ch) for ch in (name + category + feature))
    suffix = _HOOK_SUFFIXES[seed % len(_HOOK_SUFFIXES)]
    keyword = re.sub(r"\s+", "", f"{feature}{suffix}")
    return keyword[:20] or "찐포인트"


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
    cta_keyword = cta_keyword.strip() or suggest_comment_keyword(product)

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
            prompt = f"""당신은 한국 Threads에서 활동하는 20~30대 여성 소셜커머스 콘텐츠 크리에이터입니다.
말투는 광고회사 카피라이터가 아니라 친한 친구에게 카톡하듯 자연스럽고 편한 대화체로 씁니다.
읽는 사람이 '친구가 괜찮은 거 하나 발견해서 알려주는 느낌'을 받게 하세요.

[화자/문체]
- 20~30대 여성 화자의 자연스러운 시선과 어휘를 사용합니다.
- 딱딱한 존댓말·보도자료체·쇼핑몰 상세페이지체를 피하고, 짧은 문장과 구어체를 섞습니다.
- '이거 은근 괜찮더라', '이런 거 찾던 사람?', '나였으면 이 포인트부터 볼 듯' 같은 친근한 리듬은 허용합니다.
- 다만 실제 사용한 사실이 없으므로 '내가 써봤는데', '며칠 써보니', '직접 샀다' 같은 가짜 체험담은 절대 만들지 않습니다.
- 이모지는 0~2개만 자연스럽게 사용하고 억지 유행어·과한 애교는 피합니다.
- 첫 1~2문장은 스크롤을 멈추게 하는 호기심/공감 훅으로 시작합니다.

[목표]
조회수만 노리는 낚시가 아니라 실제 귀속 순이익 최대화 + SEO/GEO/AEO 동시 최적화입니다.
광고문구처럼 밀어붙이지 말고 친구끼리 정보 공유하는 느낌으로 작성하세요.
상품 DB에 없는 성능, 인증, 배송일, 할인율, 최저가, 후기, 재고 희소성을 추측하거나 만들지 마세요.
본문은 500자 이하, 과장표현·허위후기·가짜 사용경험 금지입니다.

[댓글 CTA]
- 마지막은 댓글을 달고 싶게 만드는 한 문장으로 끝냅니다.
- 댓글 키워드는 정확히 '{cta_keyword}'를 사용합니다.
- 예: "포인트 더 궁금하면 댓글에 '{cta_keyword}' 남겨줘. 내가 보기 쉽게 정리해줄게 :)"
- 강압적 구매 유도, 허위 마감임박, 거짓 품절, 거짓 할인은 금지합니다.

[SEO]
- 핵심 검색어를 첫 1~2문장 안에 자연스럽게 사용합니다.
- 키워드 나열 대신 검색 의도에 맞는 문장을 만듭니다.
- 상품명·카테고리·브랜드를 검색 가능한 표현으로 연결합니다.

[GEO]
- AI가 이해하기 쉬운 명확한 사실 문장을 포함합니다.
- 상품 DB에 존재하는 엔티티와 사실만 사용합니다.
- 무엇인지, 누구에게 필요한지, 무엇을 비교해야 하는지 명확히 씁니다.

[AEO]
- 실제 구매자가 친구에게 물어볼 법한 질문을 최소 1개 포함합니다.
- 질문 직후 핵심 답변을 먼저 제시합니다.

상품정보(JSON): {json.dumps(product, ensure_ascii=False)}
검색최적화 컨텍스트(JSON): {json.dumps(search_ctx, ensure_ascii=False)}
수익성 피드백(JSON): {feedback_text}
콘텐츠 각도: {ANGLES[angle]}
댓글 CTA 키워드: {cta_keyword}
후보 수: {count}

수익성 피드백에 충분한 주문 표본이 있으면 순이익과 Content Score가 높은 패턴을 우선하고,
순이익이 음수이거나 반품률이 높은 패턴은 모방하지 마세요. 표본이 적으면 과적합하지 마세요.

JSON 배열만 반환하세요.
각 항목: {{"body":"...","cta_keyword":"{cta_keyword}","score":0~100,"reason":"..."}}
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
                    keyword = str(row.get("cta_keyword", cta_keyword)).strip()[:100] or cta_keyword
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
    keyword = cta_keyword.strip() or suggest_comment_keyword(product)
    name = str(product.get("name") or "이 상품")
    category = str(product.get("category") or "제품")

    friendly_prefix = {
        "problem_solution": f"{category} 찾는 사람? 나였으면 일단 내 용도에 맞는지부터 볼 것 같아. ",
        "experience": f"{category} 볼 때 광고 문구보다 실제로 확인되는 포인트부터 보는 편이거든. ",
        "question": f"{category} 고를 때 다들 뭐부터 봐? 나는 이런 건 기본 정보부터 체크하게 되더라. ",
        "comparison": f"가격만 보고 고르기엔 좀 아쉽잖아. {category}는 용도랑 조건 같이 보는 게 낫더라. ",
        "listicle": f"{category} 살 때 이것만은 보자. 용도, 옵션·규격, 최종 판매조건. 딱 세 가지. ",
    }.get(angle, "")

    # 규칙 기반 fallback도 너무 딱딱하지 않게 마무리 CTA를 친근하게 붙인다.
    base_body = base_body.replace("입니다.", "이야.").replace("하세요.", "해봐.")
    cta_line = f" 더 궁금한 포인트 있으면 댓글에 '{keyword}' 남겨줘. 보기 쉽게 정리해줄게 :)"

    result = []
    for i in range(count):
        intro = friendly_prefix if i == 0 else f"{name}, 은근 비교할 포인트가 있더라. "
        body = (intro + base_body + cta_line)[:500]
        search_scores = optimization_scores(body, search_ctx)
        result.append({
            "body": body,
            "cta_keyword": keyword,
            "score": 70.0 if feedback_used else 67.0,
            "reason": "친근한 여성 화자 + 순이익 전략 + SEO/GEO/AEO 안전 초안" if feedback_used else "친근한 여성 화자 + SEO/GEO/AEO 규칙 기반 초안",
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
