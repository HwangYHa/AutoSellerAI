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
            "평소 말하기 애매하지만 실제로 신경 쓰이는 작은 불편이나 욕구 하나를 잡아 시작한다. "
            "감정은 조금 세게 잡아도 되지만 제품이 해결한다고 단정할 때는 반드시 확인된 근거가 있어야 한다."
        ),
        "experience": (
            "후기처럼 생생한 1인칭 관찰 톤으로 쓴다. '솔직히 딱 봤을 때', '나였으면', '이런 건 괜히 한 번 더 보게 되더라' 같은 "
            "표현은 적극 사용해도 된다. 단 실제 구매·배송·사용 경험을 했다고 거짓말하지 않는다."
        ),
        "question": (
            "친구 사이에서 살짝 자극적으로 던질 법한 한 문장 질문으로 시작한다. 질문 직후 바로 자기 생각을 말하고, "
            "확인된 제품 포인트를 1~3개만 자연스럽게 끼워 넣는다."
        ),
        "comparison": (
            "타사 스펙을 지어내지 않는다. 대신 취향과 선택 기준을 선명하게 갈라서 '이쪽 취향이면 눈 갈 만하고, "
            "다른 조건이 우선이면 그걸 먼저 보면 된다'처럼 독자가 자기 편을 고르게 한다."
        ),
        "listicle": (
            "3개 안팎의 포인트를 짧고 세게 쓴다. 정보표처럼 설명하지 말고 친구가 '이건 봐, 이건 넘겨'라고 "
            "콕 집어주는 느낌으로 만든다."
        ),
    }.get(angle, "친구가 발견한 제품을 살짝 들뜬 톤으로 공유하되 제품 사실은 지어내지 않는다.")


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
        "origin_overexposure", "spec_gap_disclaimer", "fabricated_personal_experience",
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
            candidate_count = min(12, max(count + 3, count * 3))
            prompt = f"""당신은 한국 Threads에서 실제로 반응을 만드는 20~30대 여성 소셜커머스 크리에이터입니다.
목표는 제품 설명문이 아니라 '친구가 살짝 흥분해서 보내온 후기 같은 글'을 만드는 것입니다.
읽는 사람이 스크롤을 멈추고, 자기 취향이나 상황을 떠올리고, 제품을 한 번 더 보고 싶게 만드세요.

[후기톤과 과장의 허용 범위]
- 감정, 분위기, 호기심, 상황은 실제 친구 대화처럼 조금 과장하고 자극적으로 표현해도 됩니다.
- 예: '솔직히 딱 봤을 때 이런 건 취향 맞으면 계속 눈 가더라', '괜히 한 번 더 눌러보게 되는 타입', '이런 거 혼자 고를 때 더 오래 보게 되지 않아?'
- '딱 보고 든 생각', '나였으면', '이런 스타일 좋아하면', '은근 신경 쓰이더라'처럼 관찰/취향 기반 1인칭 표현은 적극 허용합니다.
- 일반적인 사용 상황, 감정, 망설임, 취향 장면은 상상해서 써도 됩니다. 이것이 콘텐츠의 생동감을 만듭니다.
- 단, '내돈내산', '내가 샀는데', '배송받아보니', '직접 써봤는데', '사용해보니', '재구매'처럼 실제 구매·사용을 했다고 속이는 문장은 금지합니다.
- 상상으로 제품의 기능/성능/효과/인증/수치/구성품을 만들어내는 것도 금지합니다. 상상은 상황과 감정에만 사용하세요.

[절대 금지]
- NEVER_EXPOSE에 있는 SKU, source_id, 숫자 카테고리, 원산지, 공급가, 내부 상태를 소비자 문장에 쓰지 마세요.
- '중국 제품', '중국산'처럼 원산지를 자발적으로 꺼내지 마세요. 소셜 판매 카피의 후킹 포인트가 아닙니다.
- '상세 스펙 정보가 많지 않아서', '정보가 부족해서', '스펙이 없어서', '확인되는 정보만 보면' 같은 구매욕을 꺾는 면피성 문장을 절대 쓰지 마세요.
- 모르는 스펙이 있으면 '모른다/없다/부족하다'고 말하는 대신 그 스펙 자체를 본문에서 빼세요.
- 공급처 원본 제목이 SEO 키워드를 길게 나열해도 그대로 복사하지 마세요. display_name만 사용하세요.
- 가격만 보고 '저렴하다/부담 없다/진입장벽 낮다/입문용이다'라고 평가하지 마세요. 비교 근거가 없습니다.
- '기본기에 충실', '무난하다', '정품이면 괜찮다' 같은 근거 없는 평가를 만들지 마세요.
- 확인되지 않은 소재 안전성, 진동 단계, 방수, 충전 방식, 사이즈, 효과, 인증, 후기, 배송, 할인, 재고를 사실처럼 만들지 마세요.
- 'Q. / A.', '찾고 계신가요?', 키워드 나열, 쇼핑몰 상세페이지 말투를 쓰지 마세요.
- 같은 CTA를 두 번 쓰지 마세요.

[상품을 보는 방식]
- PUBLIC_FACTS와 상세 텍스트에서 '사람이 실제로 관심 가질 만한 포인트'만 골라 쓰세요. DB 필드를 전부 읊지 마세요.
- 함께 첨부된 상품 이미지는 아주 중요합니다. 눈에 실제로 보이는 색상, 형태, 버튼, 패키지, 외형 분위기, 디자인 인상을 적극 활용하세요.
- 이미지에서 확인되는 디자인을 보고 '취향 맞으면 눈길 갈 만하다', '딱 봤을 때 이런 느낌' 같은 주관적 반응을 만드는 것은 허용합니다.
- 이미지에서 보이지 않는 기능이나 성능은 추측하지 마세요.
- 가격도 매번 넣지 마세요. 가격이 이야기의 핵심일 때만 사실값으로 사용하세요.
- 정보가 적으면 없는 정보를 언급하지 말고, 이미지·이름·확인된 포인트와 일반적인 구매 상황을 바탕으로 더 짧고 강하게 쓰세요.

[말투]
- 친구 한 명에게 DM 보내듯 씁니다. 광고 카피가 아니라 사적인 대화처럼 들려야 합니다.
- 첫 문장은 가능하면 상품명이 아니라 상황/감정/호기심으로 시작합니다.
- 20~30대 여성 화자이되 억지 애교는 금지하고, 약간 솔직하고 장난기 있는 톤을 허용합니다.
- 짧은 문장, 자연스러운 줄바꿈, 한 문단 1~3문장.
- 상품명은 본문 전체에서 보통 0~1회면 충분합니다.
- '추천합니다/확인하세요/필요합니다'보다 '나였으면/솔직히/이런 건/은근/괜히' 같은 구어체를 우선합니다.
- 구매를 대놓고 명령하지 말고 호기심과 욕구를 키워서 스스로 더 보게 만드세요.

[판매 흐름]
상황 또는 욕구 → 살짝 자극적인 공감/반응 → 눈에 보이거나 확인되는 제품 포인트 → 왜 눈길이 가는지 → 짧은 CTA.
제품을 설명하려 하지 말고 '이 제품을 보고 친구가 어떤 말을 할지'를 먼저 생각하세요.

[선택한 유형: {ANGLES[angle]}]
{_angle_instruction(angle)}

[형식]
- 500자 이하, 보통 3~6개의 짧은 문단.
- 댓글 키워드 '{cta_keyword}'는 맨 마지막 CTA에서 정확히 한 번만 사용합니다.
- 후보끼리 훅, 감정, 상황, 전개를 확실히 다르게 만드세요.
- SEO는 사람 눈에 티 나지 않게 한두 표현만 자연스럽게 녹이세요. 키워드 나열은 실패입니다.

CUSTOMER EVIDENCE(JSON):
{json.dumps(customer_evidence, ensure_ascii=False, default=str)}

SEARCH CONTEXT(JSON):
{json.dumps(search_ctx, ensure_ascii=False, default=str)}

PERFORMANCE FEEDBACK(JSON):
{feedback_text}

각 후보를 쓰기 전에 내부적으로 '이 글을 친구가 왜 보내는지 / 읽는 사람이 어느 문장에서 꽂힐지'를 정하세요.
그 기획 과정은 본문에 노출하지 마세요.
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
                max_tokens=4800,
                temperature=0.92,
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
                        "reason": str(row.get("reason", "후기톤·정밀 상품분석 기반 판매 카피"))[:240],
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
    options = public.get("options") or []
    keyword = cta_keyword.strip() or suggest_comment_keyword(product)
    search_ctx = build_search_context(product)

    fact_bits: list[str] = []
    if material:
        fact_bits.append(f"소재는 {material}")
    if options:
        fact_bits.append(f"고를 수 있는 옵션이 {len(options)}개")
    fact_line = " · ".join(fact_bits[:2])

    adult = _is_adult_product(product)
    if adult:
        hooks = {
            "problem_solution": "혼자 고르는 거라고 대충 사고 싶진 않잖아. 오히려 이런 게 취향 더 많이 타는 것 같아.",
            "experience": "솔직히 이런 건 딱 봤을 때 취향 맞으면 괜히 한 번 더 보게 되지 않아?",
            "question": "이런 거 고를 때 너는 기능부터 봐, 아니면 딱 봤을 때 끌리는지부터 봐?",
            "comparison": "비슷비슷해 보여도 이상하게 눈이 계속 가는 건 따로 있더라.",
            "listicle": "이런 건 길게 볼 필요 없더라. 나는 딱 세 가지만 볼 것 같아.",
        }
        alternate_hooks = (
            "남들한테 물어보기 애매한 제품일수록 결국 내 취향이 제일 정확하더라.",
            "괜히 이런 거 검색하다 보면 처음엔 다 비슷해 보이는데, 보다 보면 취향 확 갈리더라.",
        )
    else:
        hooks = {
            "problem_solution": f"{category} 하나 고르는데 왜 이렇게 다 비슷해 보이는지 모르겠더라. 결국 내 상황에 꽂히는 포인트가 있어야 해.",
            "experience": f"솔직히 {category}는 스펙 다 읽기 전에 딱 눈에 들어오는 포인트가 먼저 있더라.",
            "question": f"{category} 고를 때 너는 가격부터 봐, 아니면 딱 봤을 때 끌리는 포인트부터 봐?",
            "comparison": f"{category}, 비슷한 제품 많아도 계속 눈 가는 건 따로 있더라.",
            "listicle": f"{category} 볼 때 나는 딱 세 가지만 먼저 볼 것 같아.",
        }
        alternate_hooks = (
            "제품 하나 고르는데 정보가 너무 많으면 오히려 더 못 고르겠더라.",
            "결국 남들이 좋다는 말보다 내가 계속 눈 가는 포인트 하나가 더 중요하더라.",
        )

    if fact_line:
        middle = f"{name}는 {fact_line}. 숫자만 보는 것보다 이게 내 취향이나 쓰려는 상황이랑 맞는지 보는 게 더 빠를 것 같아."
    else:
        middle = f"{name}, 사진 보고 한 번 더 눈이 갔다면 일단 그게 시작인 것 같아. 이런 건 남들 기준보다 내가 보자마자 어떤 느낌이 드는지가 은근 크잖아."

    if angle == "listicle":
        middle = (
            f"1) 딱 봤을 때 내 취향인지\n2) 내가 진짜 중요하게 보는 조건이 뭔지\n3) 사고 나서도 손이 갈 것 같은지\n\n"
            f"{name}도 이 세 개 기준으로 보면 훨씬 빨리 감 올 것 같아."
        )

    result: list[dict[str, Any]] = []
    for i in range(count):
        hook = hooks.get(angle, hooks["problem_solution"]) if i == 0 else alternate_hooks[(i - 1) % len(alternate_hooks)]
        body = _normalize_body(
            f"{hook}\n\n{middle}\n\n"
            f"궁금한 포인트 있으면 댓글에 '{keyword}' 남겨줘. 내가 보기 쉽게 같이 정리해볼게."
        )
        quality_score, issues = sales_copy_score(body, evidence, keyword)
        scores = optimization_scores(body, search_ctx)
        result.append({
            "body": body,
            "cta_keyword": keyword,
            "score": min(80.0, max(58.0, quality_score - 10)),
            "reason": "AI 실패 시에도 후기톤·자극적 훅은 유지하고 거짓 사용후기·원산지·스펙부족 문구는 제거한 초안",
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
