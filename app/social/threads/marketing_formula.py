from __future__ import annotations

import re
from typing import Any

from app.social.threads.content_engine import generate_threads_content as _base_generate_threads_content

FORMULA_VERSION = "threads-5-factor-v1"
REFERENCE_REPOST_MIN = 10
REFERENCE_SHARE_MIN = 10

_RECIPROCAL_ENGAGEMENT_TERMS = (
    "맞팔", "선팔", "팔로우반사", "좋아요반사", "좋반", "댓글품앗이", "품앗이",
    "스알", "선하리", "바아리",
)
_QUESTION_HINTS = ("어때", "어떤", "뭐가", "왜", "맞아", "할까", "일까", "인가", "고를", "봤어")
_SURPRISE_HINTS = ("오히려", "반대로", "의외", "사실", "근데", "그런데", "보다", "더")
_VALUE_HINTS = (
    "원", "개", "분", "시간", "년", "회", "cm", "mm", "kg", "g", "ml",
    "소재", "옵션", "브랜드", "구성", "기능", "방수", "충전", "크기", "무게",
)
_ENGAGEMENT_HINTS = ("댓글", "의견", "궁금", "너는", "여러분은", "골라", "알려줘", "어떻게 생각")


def reference_is_worthy(reposts: int, shares: int) -> bool:
    """Return whether a post meets the working reference threshold.

    The marketing playbook uses posts with at least 10 reposts AND 10 shares as
    reference candidates. This is a curation rule for research, not a claim about
    the Threads ranking algorithm itself.
    """
    return int(reposts or 0) >= REFERENCE_REPOST_MIN and int(shares or 0) >= REFERENCE_SHARE_MIN


def _nonempty_lines(body: str) -> list[str]:
    return [line.strip() for line in str(body or "").splitlines() if line.strip()]


def _contains_number(text: str) -> bool:
    return bool(re.search(r"\d", text or ""))


def _hook_score(first_line: str) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    lowered = first_line.lower()

    if 0 < len(first_line) <= 70:
        score += 7
        signals.append("첫 문장이 짧음")
    if _contains_number(first_line):
        score += 7
        signals.append("숫자 후킹")
    if "?" in first_line or any(hint in first_line for hint in _QUESTION_HINTS):
        score += 6
        signals.append("질문 후킹")
    if any(hint in lowered for hint in _SURPRISE_HINTS):
        score += 5
        signals.append("의외성/반전")

    return min(score, 25), signals


def audit_threads_body(
    body: str,
    *,
    has_media: bool = False,
    product_name: str = "",
) -> dict[str, Any]:
    """Score a Threads draft against the five-factor marketing playbook.

    This score intentionally measures execution quality, not guaranteed reach.
    It is blended with the existing content/evidence score only for ranking draft
    candidates on the Social Commerce Threads page.
    """
    text = str(body or "").strip()
    lines = _nonempty_lines(text)
    first_line = lines[0] if lines else ""
    paragraph_count = len([p for p in re.split(r"\n\s*\n", text) if p.strip()]) if text else 0
    average_line_length = round(sum(len(line) for line in lines) / max(1, len(lines)), 1)

    hook_score, hook_signals = _hook_score(first_line)

    readability_score = 0
    readability_signals: list[str] = []
    if 3 <= paragraph_count <= 8:
        readability_score += 8
        readability_signals.append("3~8개 짧은 문단")
    elif paragraph_count >= 2:
        readability_score += 5
    if average_line_length <= 48:
        readability_score += 7
        readability_signals.append("짧은 문장")
    elif average_line_length <= 65:
        readability_score += 4
    if 80 <= len(text) <= 500:
        readability_score += 5
        readability_signals.append("Threads 길이 적정")
    readability_score = min(readability_score, 20)

    value_score = 0
    value_signals: list[str] = []
    if _contains_number(text):
        value_score += 7
        value_signals.append("구체적 숫자")
    matched_value_hints = [hint for hint in _VALUE_HINTS if hint.lower() in text.lower()]
    if matched_value_hints:
        value_score += min(8, 2 + len(set(matched_value_hints)))
        value_signals.append("구체적 강점/스펙")
    if product_name and product_name.strip() and product_name.strip() not in first_line:
        value_score += 5
        value_signals.append("상품명보다 관심 주제로 시작")
    elif not product_name:
        value_score += 3
    value_score = min(value_score, 20)

    engagement_score = 0
    engagement_signals: list[str] = []
    if "?" in text:
        engagement_score += 5
        engagement_signals.append("대화형 질문")
    if any(hint in text for hint in _ENGAGEMENT_HINTS):
        engagement_score += 5
        engagement_signals.append("댓글/의견 유도")
    engagement_score = min(engagement_score, 10)

    media_score = 10 if has_media else 0
    media_signals = ["사진/영상 근거 있음"] if has_media else []

    broad_topic_score = 15
    broad_topic_signals = ["상품 직판형 훅 아님"]
    direct_sales_markers = ("지금 구매", "바로 구매", "최저가", "특가", "구매하세요", "주문하세요")
    if any(marker in first_line for marker in direct_sales_markers):
        broad_topic_score = 3
        broad_topic_signals = ["직판형 첫 문장"]
    elif product_name and product_name.strip() and first_line.startswith(product_name.strip()):
        broad_topic_score = 8
        broad_topic_signals = ["상품명으로 시작")]

    penalties: list[str] = []
    penalty = 0
    for term in _RECIPROCAL_ENGAGEMENT_TERMS:
        if term in text.replace(" ", ""):
            penalty += 20
            penalties.append(f"상호작용 품앗이 표현: {term}")
            break

    score = max(
        0,
        min(
            100,
            hook_score + readability_score + value_score + engagement_score + media_score + broad_topic_score - penalty,
        ),
    )

    return {
        "score": int(score),
        "hook_score": hook_score,
        "readability_score": readability_score,
        "value_score": value_score,
        "engagement_score": engagement_score,
        "media_score": media_score,
        "broad_topic_score": broad_topic_score,
        "paragraph_count": paragraph_count,
        "average_line_length": average_line_length,
        "signals": hook_signals + readability_signals + value_signals + engagement_signals + media_signals + broad_topic_signals,
        "penalties": penalties,
        "version": FORMULA_VERSION,
    }


def _has_product_media(product: dict[str, Any]) -> bool:
    for key in ("images", "detail_images"):
        values = product.get(key) or []
        if isinstance(values, str):
            if values.strip() and values.strip() not in {"[]", "{}"}:
                return True
        elif values:
            return True
    return False


def rerank_variants_with_formula(product: dict[str, Any], variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has_media = _has_product_media(product)
    product_name = str(product.get("name") or "").strip()
    ranked: list[dict[str, Any]] = []

    for variant in variants:
        row = dict(variant)
        audit = audit_threads_body(
            str(row.get("body") or ""),
            has_media=has_media,
            product_name=product_name,
        )
        base_score = float(row.get("score") or 0)
        combined_score = round(base_score * 0.75 + float(audit["score"]) * 0.25, 1)
        row["base_score"] = base_score
        row["formula_score"] = audit["score"]
        row["formula_checks"] = audit
        row["formula_version"] = FORMULA_VERSION
        row["score"] = combined_score
        reason = str(row.get("reason") or "").strip()
        formula_reason = f"Threads 반응도 공식 {audit['score']}점"
        row["reason"] = f"{reason} · {formula_reason}" if reason else formula_reason
        ranked.append(row)

    ranked.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return ranked


def generate_threads_content_with_formula(
    product: dict[str, Any],
    angle: str = "problem_solution",
    cta_keyword: str = "",
    count: int = 3,
    performance_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    variants = _base_generate_threads_content(
        product,
        angle=angle,
        cta_keyword=cta_keyword,
        count=count,
        performance_context=performance_context,
    )
    return rerank_variants_with_formula(product, variants)


__all__ = [
    "FORMULA_VERSION",
    "REFERENCE_REPOST_MIN",
    "REFERENCE_SHARE_MIN",
    "audit_threads_body",
    "generate_threads_content_with_formula",
    "reference_is_worthy",
    "rerank_variants_with_formula",
]
