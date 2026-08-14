from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from app.config import get_settings
from app.social.threads.copy_quality import marketing_evidence, natural_product_name, sales_copy_score
from app.social.threads.product_analysis import build_product_evidence, primary_product_image
from app.social.threads.search_optimization import build_search_context, optimization_scores

logger = logging.getLogger(__name__)


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
_ADULT_TERMS = ("성인용품", "자위기구", "바이브레이터", "진동기", "딜도", "섹스토이")
_HOOK_SUFFIXES = ("찐포인트", "왜핫해", "궁금해", "비교해줘", "실사용팁")
_ADULT_HOOKS = ("선택팁", "입문팁", "비교포인트", "관리팁", "체크포인트")


def _clean_tokens(text: str) -> list[str]:
    return [x for x in re.sub(r"[^0-9A-Za-z가-힣 ]", " ", text or "").split() if len(x) >= 2]


def _normalize_body(body: str) -> str:
    text = str(body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?m)^\s*(?:결론|요약|핵심|POINT|포인트)\s*[:：]\s*", "", text)
    return text[:500].strip()


def _is_adult_product(product: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(product.get(key) or "") for key in ("name", "category", "brand")
    ).lower()
    return any(term.lower() in haystack for term in _ADULT_TERMS)


def suggest_comment_keyword(product: dict[str, Any]) -> str:
    """Create a short comment hook without turning SEO terms into an awkward CTA."""
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
    seed = sum(ord(ch) for ch in (name + category + feature))

    if _is_adult_product({**product, **verified}) and not feature:
        return _ADULT_HOOKS[seed % len(_ADULT_HOOKS)]

    if not feature:
        search_ctx = build_search_context({**product, **verified})
        candidates = list(search_ctx.get("related_keywords") or [])
        candidates += _clean_tokens(natural_product_name(verified))
        feature = next((str(x).strip() for x in candidates if str(x).strip()), "상품")

    suffix = _HOOK_SUFFIXES[seed % len(_HOOK_SUFFIXES)]
    keyword = re.sub(r"\s+", "", f"{feature}{suffix}")
    return keyword[:20] or "찐포인트"


def _angle_instruction(angle: str) -> str:
    return {
        "problem_solution": (
            "사람이 실제로 느끼는 작은 불편이나 망설임 하나로 시작한다. 해결책을 과장하지 말고, "
            "확인된 제품 포인트가 그 상황에서 왜 의미 있는지를 연결한다."
        ),
        "experience": (
            "가짜 사용후기는 절대 금지한다. 대신 친구가 제품을 같이 보면서 '이런 상황이면 이 부분부터 볼 것 같다'고 "
            "말하는 공감형 흐름으로 쓴다. 제품 설명보다 상황과 감정을 먼저 둔다."
        ),
        "question": (
            "친구에게 진짜 물어볼 법한 한 문장 질문으로 시작한다. 질문 직후 바로 핵심 답을 주고, "
            "제품의 확인된 근거를 1~3개만 자연스럽게 이어간다."
        ),
        "comparison": (
            "근거 없는 타사 비교는 금지한다. 대신 '이 조건이 중요한 사람 / 다른 조건이 중요한 사람'처럼 구매 기준을 나눠서 "
            "독자가 자기 취향을 스스로 고르게 한다."
        ),
        "listicle": (
            "3개 안팎의 짧은 체크포인트로 쓴다. 각 항목은 정보표가 아니라 친구가 '이것만 봐'라고 짚어주는 한 문장으로 만든다."
        ),
    }.get(angle, "친구가 발견한 제품을 자연스럽게 공유하는 흐름으로 쓴다.")


def _model_name(settings) -> str:
    return (
        str(os.getenv("THREADS_CONTENT_MODEL", "") or "").strip()
        or str(getattr(settings, "claude_model_heavy", "") or "").strip()
        or str(settings.claude_model).strip()
    )


def _image_urls(evidence: dict[str, Any], limit: int = 2) -> list[str]:
    verified = evidence.get("verified") or {}
    rows = [*(verified.get("images") or []), *(verified.get("detail_images") or [])]
    result: list[str] = []
    for value in rows:
        candidates: list[str] = []
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, dict):
            candidates = [str(value.get(k) or "") for k in ("url", "src", "image_url", "imageUrl")]
        for url in candidates:
            url = url.strip()
            if url.startswith("https://") and url not in result:
                result.append(url)
                break
        if len(result) >= limit:
            break
    return result


def _critical_quality_issue(issues: list[str]) -> bool:
    critical = {
        "empty", "internal_sku", "internal_source_id", "internal_code",
        "numeric_category", "keyword_stuffing", "unsupported_or_template_judgment",
    }
    return bool(critical.intersection(issues))


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

    customer_evidence = marketing_evidence(evidence)
    search_ctx = build_search_context(enriched_product)
    cta_keyword = cta_keyword.strip() or suggest_comment_keyword(enriched_product)
    image_url = primary_product_image(enriched_product)
    image_urls = _image_urls(evidence, 2)

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
            candidate_count = min(10, max(count + 2, count * 2))
            prompt = f"""당신은 한국 Threads에서 실제로 반응을 만드는 20~30대 여성 소셜커머스 크리에이터입니다.
목표는 상품정보를 요약하는 것이 아니라, 독자가 '어? 이건 내 얘기인데' 하고 멈춘 뒤 제품을 더 보고 싶게 만드는 것입니다.

[절대 금지]
- NEVER_EXPOSE에 있는 SKU, source_id, 숫자 카테고리, 공급가, 내부 상태를 소비자 문장에 쓰지 마세요.
- 공급처 원본 제목이 SEO 키워드를 길게 나열해도 그대로 복사하지 마세요. display_name을 사용하세요.
- 가격만 보고 '저렴하다/부담 없다/진입장벽 낮다/입문용이다'라고 평가하지 마세요. 비교 근거가 없습니다.
- '기본기에 충실', '무난하다', '정품이면 괜찮다', '원산지가 중국이어도 괜찮다' 같은 근거 없는 평가를 만들지 마세요.
- 확인되지 않은 기능, 소재 안전성, 진동 단계, 방수, 충전 방식, 사이즈, 효과, 인증, 후기, 배송, 할인, 재고를 추측하지 마세요.
- 'Q. / A.', '찾고 계신가요?', 검색 키워드 나열, 쇼핑몰 SEO 문장을 쓰지 마세요.
- 같은 CTA를 두 번 쓰지 마세요.

[상품을 보는 방식]
- PUBLIC_FACTS와 상세 텍스트를 가장 중요한 근거로 사용하세요.
- 함께 첨부된 상품 이미지는 '눈에 실제로 보이는 사실'만 근거로 사용할 수 있습니다. 예: 색상, 형태, 버튼이 보이는지, 패키지 구성, 외형 디자인.
- 이미지에서 보이지 않는 기능이나 성능은 추측하지 마세요.
- LOW_PRIORITY_FACTS의 원산지나 가격은 그 콘텐츠의 핵심 구매 판단에 정말 필요할 때만 씁니다. 매번 넣지 마세요.
- 정보가 부족하면 부족한 정보를 억지로 언급하며 구매욕을 떨어뜨리지 말고, 확인된 매력 포인트만 좁게 깊게 이야기하세요.

[말투]
- 친구 한 명에게 DM 보내듯 씁니다. 설명문이 아니라 대화입니다.
- 첫 문장은 상품명이 아니라 상황/감정/호기심으로 시작하는 것을 우선합니다.
- 20~30대 여성 화자이되 억지 애교, 과한 유행어, 광고회사 카피 느낌은 금지합니다.
- 짧은 문장, 자연스러운 줄바꿈, 한 문단 1~3문장 정도.
- 독자가 자기 상황을 떠올리게 하되 가짜 체험담은 쓰지 않습니다.
- 상품명은 전체 본문에서 보통 0~1회면 충분합니다.
- 가격·원산지·옵션 개수 같은 DB 필드는 필요할 때만 말하고, 단순 나열하지 않습니다.

[판매 흐름]
상황/욕구/망설임 → 공감 → 제품에서 실제로 확인되는 포인트 → 그 포인트가 왜 신경 쓰일 만한지 → 부담 없는 CTA.
'구매하세요'라고 밀지 말고, 독자가 스스로 더 보고 싶게 만드세요.

[선택한 유형: {ANGLES[angle]}]
{_angle_instruction(angle)}

[형식]
- 500자 이하, 보통 3~6개의 짧은 문단.
- 댓글 키워드 '{cta_keyword}'는 맨 마지막 CTA에서 정확히 한 번만 사용합니다.
- 후보끼리 훅, 상황, 전개 방식이 확실히 달라야 합니다.
- SEO는 사람 눈에 티 나지 않게 녹이세요. 키워드를 나열하면 실패입니다.

CUSTOMER EVIDENCE(JSON):
{json.dumps(customer_evidence, ensure_ascii=False, default=str)}

SEARCH CONTEXT(JSON):
{json.dumps(search_ctx, ensure_ascii=False, default=str)}

PERFORMANCE FEEDBACK(JSON):
{feedback_text}

먼저 각 후보마다 내부적으로 '누가/어떤 순간에/왜 관심을 가질지'를 정한 다음 본문을 쓰세요.
본문에는 그 내부 기획표를 노출하지 마세요.
후보 수: {candidate_count}

JSON 배열만 반환하세요.
각 항목: {{"body":"줄바꿈 포함 본문","cta_keyword":"{cta_keyword}","score":0~100,"reason":"한 줄"}}
"""

            content_blocks: list[dict[str, Any]] = []
            for url in image_urls:
                content_blocks.append({"type": "image", "source": {"type": "url", "url": url}})
            content_blocks.append({"type": "text", "text": prompt})

            msg = client.messages.create(
                model=_model_name(settings),
                max_tokens=4200,
                temperature=0.82,
                messages=[{"role": "user", "content": content_blocks}],
            )
            raw = "".join(getattr(block, "text", "") for block in msg.content).strip()
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                rows = json.loads(match.group())
                candidates: list[dict[str, Any]] = []
                for row in rows[:candidate_count]:
                    body = _normalize_body(str(row.get("body", "")))
                    if not body:
                        continue
                    quality_score, issues = sales_copy_score(body, evidence, cta_keyword)
                    if quality_score < 72 or _critical_quality_issue(issues):
                        continue
                    model_score = max(0.0, min(float(row.get("score", 75)), 100.0))
                    search_scores = optimization_scores(body, search_ctx)
                    final_score = round(quality_score * 0.7 + model_score * 0.3, 1)
                    candidates.append({
                        "body": body,
                        "cta_keyword": cta_keyword,
                        "score": final_score,
                        "reason": str(row.get("reason", "정밀 상품분석 기반 판매 카피"))[:240],
                        "source": "ai_profit_feedback" if performance_context else "ai",
                        "selected_angle": angle,
                        "primary_keyword": search_ctx["primary_keyword"],
                        "related_keywords": search_ctx["related_keywords"],
                        "faq_question": search_ctx["faq_question"],
                        "image_url": image_url,
                        "evidence_stats": evidence.get("evidence_stats") or {},
                        "model": _model_name(settings),
                        "quality_issues": issues,
                        **search_scores,
                    })
                candidates.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
                if len(candidates) >= count:
                    return candidates[:count]
                if candidates:
                    fallbacks = _fallback_variants(
                        enriched_product, angle, cta_keyword, count - len(candidates),
                        bool(performance_context), image_url=image_url, evidence=evidence,
                    )
                    return (candidates + fallbacks)[:count]
        except Exception as exc:
            logger.warning("Threads Claude content generation failed: %s", exc)

    return _fallback_variants(
        enriched_product, angle, cta_keyword, count, bool(performance_context),
        image_url=image_url, evidence=evidence,
    )


def _fallback_variants(
    product: dict[str, Any],
    angle: str,
    cta_keyword: str,
    count: int,
    feedback_used: bool = False,
    *,
    image_url: str = "",
    evidence: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    evidence = evidence or {"verified": dict(product)}
    verified = evidence.get("verified") or product
    public = marketing_evidence(evidence).get("public_facts") or {}
    name = str(public.get("display_name") or natural_product_name(verified) or "이 제품")
    category = str(public.get("category") or "제품")
    material = str(public.get("material") or "").strip()
    price = public.get("sell_price")
    options = public.get("options") or []
    keyword = cta_keyword.strip() or suggest_comment_keyword(product)
    search_ctx = build_search_context(product)

    facts: list[str] = []
    if material:
        facts.append(f"확인되는 소재는 {material}")
    if options:
        facts.append(f"등록된 옵션은 {len(options)}개")
    if price not in (None, ""):
        try:
            facts.append(f"현재 표시 가격은 {float(price):,.0f}원")
        except Exception:
            pass
    fact_line = ", ".join(facts[:2])

    adult = _is_adult_product(product)
    if adult:
        hooks = {
            "problem_solution": "이런 건 남들 기준보다 내 기준에 맞는지가 더 중요하잖아.",
            "experience": "혼자 고르는 제품일수록 괜히 더 오래 보게 되지 않아?",
            "question": "이런 제품 고를 때 너는 디자인부터 봐, 조건부터 봐?",
            "comparison": "비슷해 보여도 내가 중요하게 보는 포인트는 사람마다 완전 다르더라.",
            "listicle": "이런 제품 볼 때 나는 딱 세 가지만 먼저 체크할 것 같아.",
        }
    else:
        hooks = {
            "problem_solution": f"{category} 고를 때 은근 애매한 게, 내 상황에 진짜 맞는지잖아.",
            "experience": f"{category}는 스펙표보다 내가 실제로 중요하게 보는 조건부터 보게 되더라.",
            "question": f"{category} 고를 때 너는 뭐부터 보는 편이야?",
            "comparison": f"{category}, 비슷해 보여도 기준 하나 정하고 보면 훨씬 고르기 쉽더라.",
            "listicle": f"{category} 볼 때 딱 세 가지만 먼저 체크해봐.",
        }

    middles: list[str] = []
    if fact_line:
        middles.append(f"{name}는 지금 확인되는 정보만 보면 {fact_line} 정도야.")
    else:
        middles.append(f"{name}는 일단 상세에서 내가 중요하게 보는 조건부터 골라 확인하는 게 좋아.")
    middles.append("정보를 한꺼번에 다 볼 필요 없이, 내 사용 기준이랑 맞는 포인트가 있는지만 먼저 보면 돼.")

    result: list[dict[str, Any]] = []
    for i in range(count):
        hook = hooks.get(angle, hooks["problem_solution"])
        if i:
            hook = (
                "제품 하나 고르는데 정보가 너무 많으면 오히려 더 못 고르겠더라."
                if i % 2 else "결국 중요한 건 남들이 좋다는 말보다 내가 보는 기준 하나인 것 같아."
            )
        body = _normalize_body(
            f"{hook}\n\n{middles[0]}\n\n{middles[1]}\n\n"
            f"더 궁금한 부분 있으면 댓글에 '{keyword}' 남겨줘. 같이 볼 포인트만 정리해줄게."
        )
        quality_score, issues = sales_copy_score(body, evidence, keyword)
        scores = optimization_scores(body, search_ctx)
        result.append({
            "body": body,
            "cta_keyword": keyword,
            "score": min(78.0, max(55.0, quality_score - 12)),
            "reason": "AI 실패 시에도 내부 ID·SEO 나열·근거 없는 평가를 제거한 안전 판매 초안",
            "source": "rule_profit_feedback" if feedback_used else "rule",
            "selected_angle": angle,
            "primary_keyword": search_ctx["primary_keyword"],
            "related_keywords": search_ctx["related_keywords"],
            "faq_question": search_ctx["faq_question"],
            "image_url": image_url,
            "quality_issues": issues,
            **scores,
        })
    return result


def _keyword_from_name(name: str) -> str:
    words = re.sub(r"[^0-9A-Za-z가-힣 ]", " ", name).split()
    return (words[0] if words else "정보")[:20]
