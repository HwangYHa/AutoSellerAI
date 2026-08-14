from __future__ import annotations

import json
import os
import re
from typing import Any

from app.config import get_settings
from app.social.threads.product_analysis import build_product_evidence, primary_product_image
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
    "listicle": "목록형",
}

_FEATURE_MARKERS = (
    "무선", "휴대용", "충전식", "대용량", "초경량", "경량", "미니", "슬림",
    "접이식", "자동", "저소음", "방수", "세척", "멀티", "올인원", "고속",
    "강력", "컴팩트", "프리미엄", "실리콘", "스테인리스", "ABS",
)

_HOOK_SUFFIXES = ("찐포인트", "왜핫해", "궁금해", "비교해줘", "실사용팁")


def _clean_tokens(text: str) -> list[str]:
    return [x for x in re.sub(r"[^0-9A-Za-z가-힣 ]", " ", text or "").split() if len(x) >= 2]


def _normalize_body(body: str) -> str:
    """Keep Threads copy readable without turning it into a formal article."""
    text = str(body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove common LLM/article labels that feel unnatural on Threads.
    text = re.sub(r"(?m)^\s*(?:결론|요약|핵심|POINT|포인트)\s*[:：]\s*", "", text)
    return text[:500].strip()


def suggest_comment_keyword(product: dict[str, Any]) -> str:
    """Create a short curiosity hook from facts that actually exist for the product."""
    try:
        evidence = build_product_evidence(product)
        verified = evidence.get("verified") or {}
    except Exception:
        verified = product

    name = str(verified.get("name") or product.get("name") or "")
    category = str(verified.get("category") or product.get("category") or "")
    brand = str(verified.get("brand") or product.get("brand") or "")
    material = str(verified.get("material") or product.get("material") or "")
    option_text = " ".join(str(x) for x in (verified.get("options") or [])[:8])
    source = " ".join([name, category, brand, material, option_text])

    feature = next((marker for marker in _FEATURE_MARKERS if marker.lower() in source.lower()), "")
    if not feature:
        search_ctx = build_search_context({**product, **verified})
        candidates = list(search_ctx.get("related_keywords") or [])
        candidates += _clean_tokens(name)
        candidates += _clean_tokens(category)
        feature = next((str(x).strip() for x in candidates if str(x).strip()), "상품")

    seed = sum(ord(ch) for ch in (name + category + feature))
    suffix = _HOOK_SUFFIXES[seed % len(_HOOK_SUFFIXES)]
    keyword = re.sub(r"\s+", "", f"{feature}{suffix}")
    return keyword[:20] or "찐포인트"


def _angle_instruction(angle: str) -> str:
    return {
        "problem_solution": (
            "구매자가 실제로 겪을 법한 불편/고민 하나로 시작한다. 그 문제를 이 상품의 확인된 특징이 "
            "어떻게 줄일 수 있는지 연결한다. 억지로 문제를 만들거나 만능 해결책처럼 쓰지 않는다."
        ),
        "experience": (
            "직접 써봤다고 거짓말하지 않는다. 대신 친구끼리 상품을 같이 보며 '이런 상황이면 이 포인트가 "
            "은근 중요하겠다'고 공감하는 방식으로 쓴다. 생활 장면은 일반적인 맥락만 사용한다."
        ),
        "question": (
            "첫 문장을 실제 친구에게 던질 법한 짧은 질문으로 시작한다. 바로 다음 문장에서 답을 주고, "
            "상품의 확인된 특징 2~3개를 자연스럽게 이어간다. 질문을 연속으로 남발하지 않는다."
        ),
        "comparison": (
            "경쟁 상품의 사실을 모르면 특정 타사와 비교하지 않는다. 대신 구매 기준(가격/규격/소재/옵션/사용 목적 등) "
            "중 확인 가능한 항목을 기준으로 '이런 사람은 이쪽, 저런 사람은 다른 조건 확인'처럼 균형 있게 쓴다."
        ),
        "listicle": (
            "목록은 3개 정도로 짧게 구성한다. 각 항목은 한 줄 안팎으로, 설명을 길게 늘이지 않는다. "
            "Threads에서 친구가 체크리스트를 보내주는 느낌을 유지한다."
        ),
    }.get(angle, "자연스러운 정보 공유형으로 작성한다.")


def _model_name(settings) -> str:
    # A dedicated override makes quality/cost tuning possible without code changes.
    return (
        str(os.getenv("THREADS_CONTENT_MODEL", "") or "").strip()
        or str(getattr(settings, "claude_model_heavy", "") or "").strip()
        or str(settings.claude_model).strip()
    )


def generate_threads_content(
    product: dict[str, Any],
    angle: str = "problem_solution",
    cta_keyword: str = "",
    count: int = 3,
    performance_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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

    try:
        evidence = build_product_evidence(product)
        verified = evidence.get("verified") or {}
        enriched_product = {**product, **verified}
    except Exception:
        evidence = {"verified": dict(product), "evidence_stats": {}}
        enriched_product = dict(product)

    search_ctx = build_search_context(enriched_product)
    cta_keyword = cta_keyword.strip() or suggest_comment_keyword(enriched_product)
    image_url = primary_product_image(enriched_product)

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
목표는 '광고를 읽는 느낌'이 아니라 친한 친구가 괜찮아 보이는 상품을 같이 살펴보며 알려주는 느낌입니다.

[가장 중요한 원칙]
1. 아래 PRODUCT EVIDENCE에 있는 사실만 상품 사실로 사용합니다.
2. 저장된 상세정보와 옵션을 가능한 한 꼼꼼히 읽되, 콘텐츠 한 편에 모든 정보를 억지로 욱여넣지 않습니다.
3. 상세페이지/원문에 없는 기능, 효과, 인증, 후기, 배송일, 할인율, 재고 희소성, 사용 경험은 만들지 않습니다.
4. supplemental_source_page_text는 원격 페이지 보강 자료일 뿐입니다. 저장된 verified 정보와 충돌하면 verified를 우선합니다.
5. 실제 사용한 적이 없으므로 '내가 써봤는데', '며칠 써보니', '직접 샀어'처럼 가짜 체험담을 쓰지 않습니다.

[말투]
- 20~30대 여성이 친한 친구와 카톡/DM/스레드에서 이야기하듯 씁니다.
- 문장을 짧게 끊고 필요한 곳에 자연스럽게 줄바꿈합니다.
- 존댓말 광고 카피, 보도자료, 홈쇼핑 진행자, 쇼핑몰 상세페이지 말투를 피합니다.
- 억지 유행어, 과한 애교, 느낌표 도배, '무조건', '역대급', '인생템', '대박' 같은 상투적 과장은 최소화합니다.
- 불필요한 서론/결론/요약 문구를 넣지 않습니다.
- 같은 뜻을 반복하지 않습니다.
- 이모지는 정말 어울릴 때만 0~2개 사용합니다.

[판매 방식]
- 상품명을 반복해서 외치지 말고, 구매자가 자기 상황에 대입하게 만듭니다.
- 확인된 특징 → 실제 구매 판단에 왜 중요한지 → 어떤 사람에게 맞을지 순서로 자연스럽게 연결합니다.
- 장점만 나열하지 말고 확인해야 할 조건/옵션이 있다면 솔직하게 언급합니다.
- CTA 직전까지는 '사라'고 밀어붙이지 않습니다.

[선택한 유형: {ANGLES[angle]}]
{_angle_instruction(angle)}

[구성]
- 500자 이하.
- 보통 3~6개의 짧은 문단. 문단 사이 한 줄 띄움.
- 첫 1~2문장: 호기심/공감 훅.
- 중간: 확인 가능한 상품 특징 2~4개를 사람 말처럼 연결.
- 필요하면 짧은 질문 1개.
- 마지막: 댓글 키워드 '{cta_keyword}'를 정확히 한 번 사용한 자연스러운 CTA.

[검색 최적화]
- 핵심 검색어는 첫 1~2문장에 자연스럽게 한 번 사용합니다.
- SEO 키워드를 나열하지 않습니다.
- AI 검색에서 이해 가능한 명확한 사실문장을 포함하되 문체를 딱딱하게 만들지 않습니다.

PRODUCT EVIDENCE(JSON):
{json.dumps(evidence, ensure_ascii=False, default=str)}

SEARCH CONTEXT(JSON):
{json.dumps(search_ctx, ensure_ascii=False, default=str)}

PERFORMANCE FEEDBACK(JSON):
{feedback_text}

댓글 CTA 키워드: {cta_keyword}
후보 수: {count}

후보끼리 첫 문장, 전개, 표현을 서로 다르게 만드세요. 같은 문장을 단어만 바꿔 복제하지 마세요.
JSON 배열만 반환하세요.
각 항목: {{"body":"줄바꿈이 포함된 본문","cta_keyword":"{cta_keyword}","score":0~100,"reason":"왜 자연스럽고 근거에 맞는지 짧게"}}
"""
            msg = client.messages.create(
                model=_model_name(settings),
                max_tokens=3200,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                rows = json.loads(match.group())
                result = []
                for row in rows[:count]:
                    body = _normalize_body(str(row.get("body", "")))
                    if not body:
                        continue
                    keyword = str(row.get("cta_keyword", cta_keyword)).strip()[:100] or cta_keyword
                    score = float(row.get("score", 75))
                    search_scores = optimization_scores(body, search_ctx)
                    result.append({
                        "body": body,
                        "cta_keyword": keyword,
                        "score": max(0.0, min(score, 100.0)),
                        "reason": str(row.get("reason", "AI 정밀 상품분석 기반 생성"))[:240],
                        "source": "ai_profit_feedback" if performance_context else "ai",
                        "selected_angle": angle,
                        "primary_keyword": search_ctx["primary_keyword"],
                        "related_keywords": search_ctx["related_keywords"],
                        "faq_question": search_ctx["faq_question"],
                        "image_url": image_url,
                        "evidence_stats": evidence.get("evidence_stats") or {},
                        "model": _model_name(settings),
                        **search_scores,
                    })
                if result:
                    return result
        except Exception:
            # Production keeps a deterministic fallback instead of breaking the UI.
            pass

    return _fallback_variants(enriched_product, angle, cta_keyword, count, bool(performance_context), image_url=image_url)


def _fallback_variants(
    product: dict[str, Any],
    angle: str,
    cta_keyword: str,
    count: int,
    feedback_used: bool = False,
    *,
    image_url: str = "",
) -> list[dict[str, Any]]:
    base_body, search_ctx = fallback_optimized_body(product, cta_keyword)
    keyword = cta_keyword.strip() or suggest_comment_keyword(product)
    name = str(product.get("name") or "이 상품")
    category = str(product.get("category") or "제품")

    friendly_prefix = {
        "problem_solution": f"{category} 찾을 때 은근 애매한 게, 내 용도에 진짜 맞는지잖아.\n\n",
        "experience": f"{category} 같이 볼 때 나는 광고 문구보다 확인되는 정보부터 보게 되더라.\n\n",
        "question": f"{category} 고를 때 다들 뭐부터 봐?\n\n나는 일단 옵션이랑 기본 정보부터 보는 편이야.\n\n",
        "comparison": f"{category}, 가격만 보고 고르기엔 좀 아쉽잖아.\n\n용도랑 조건 같이 보는 게 훨씬 편해.\n\n",
        "listicle": f"{category} 볼 때 딱 세 가지만 먼저 체크해봐.\n\n1) 사용 목적\n2) 옵션·규격\n3) 최종 판매조건\n\n",
    }.get(angle, "")

    base_body = base_body.replace("입니다.", "이야.").replace("하세요.", "해봐.")
    cta_line = f"\n\n더 궁금하면 댓글에 '{keyword}' 남겨줘. 보기 쉽게 같이 정리해볼게 :)"

    result = []
    for i in range(count):
        intro = friendly_prefix if i == 0 else f"{name}, 보면 볼수록 체크할 포인트가 좀 있더라.\n\n"
        body = _normalize_body(intro + base_body + cta_line)
        search_scores = optimization_scores(body, search_ctx)
        result.append({
            "body": body,
            "cta_keyword": keyword,
            "score": 70.0 if feedback_used else 67.0,
            "reason": "친근한 여성 화자 + 순이익 전략 + 근거 기반 안전 초안" if feedback_used else "친근한 여성 화자 + 근거 기반 규칙 초안",
            "source": "rule_profit_feedback" if feedback_used else "rule",
            "selected_angle": angle,
            "primary_keyword": search_ctx["primary_keyword"],
            "related_keywords": search_ctx["related_keywords"],
            "faq_question": search_ctx["faq_question"],
            "image_url": image_url,
            **search_scores,
        })
    return result


def _keyword_from_name(name: str) -> str:
    words = re.sub(r"[^0-9A-Za-z가-힣 ]", " ", name).split()
    return (words[0] if words else "정보")[:20]
