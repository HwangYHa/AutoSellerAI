from __future__ import annotations

import re
from typing import Any

from app.social.threads.content_engine import generate_threads_content


HOOK_UNEXPECTED = (
    "오히려",
    "근데",
    "의외",
    "반대로",
    "사실",
    "놀랍게",
    "문제는",
    "진짜",
)
VALUE_WORDS = (
    "가격",
    "옵션",
    "소재",
    "브랜드",
    "구성",
    "사이즈",
    "용량",
    "무게",
    "디자인",
    "기능",
)
ENGAGEMENT_WORDS = (
    "댓글",
    "어때",
    "너는",
    "궁금",
    "골라",
    "뭐가",
    "어떤",
    "공유",
    "저장",
)


def _first_content_line(body: str) -> str:
    for line in str(body or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _hook_type(first_line: str) -> str:
    if re.search(r"\d", first_line):
        return "number"
    if "?" in first_line or any(word in first_line for word in ("너는", "혹시", "어떤", "뭐가", "왜")):
        return "question"
    if any(word in first_line for word in HOOK_UNEXPECTED):
        return "unexpected"
    return "plain"


def score_threads_playbook(body: str, product: dict[str, Any] | None = None, image_url: str = "") -> tuple[float, dict[str, bool | str]]:
    """Score a draft against the practical Threads marketing rules used by the UI.

    The score is intentionally heuristic. It is not a claim about the Threads
    ranking algorithm; it rewards the content construction principles we want
    AutoSellerAI to consistently apply before publishing.
    """
    product = product or {}
    text = str(body or "").strip()
    first = _first_content_line(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    hook_type = _hook_type(first)

    product_name = str(product.get("name") or "").strip()
    starts_with_product = bool(product_name and first and first.startswith(product_name[: min(14, len(product_name))]))
    broad_topic = bool(first) and not starts_with_product and len(first) <= 70
    strong_hook = hook_type != "plain"

    avg_line_len = sum(len(line) for line in lines) / max(1, len(lines))
    short_readable = 3 <= len(lines) <= 12 and avg_line_len <= 48

    value_proof = any(word in text for word in VALUE_WORDS)
    for field in ("brand", "material"):
        value = str(product.get(field) or "").strip()
        if value and value.lower() in text.lower():
            value_proof = True
            break

    visual_ready = bool(str(image_url or "").strip())
    engagement = "?" in text or any(word in text for word in ENGAGEMENT_WORDS)

    score = 0.0
    score += 22 if broad_topic else 8
    score += 23 if strong_hook else 8
    score += 20 if value_proof else 7
    score += 17 if short_readable else 6
    score += 10 if visual_ready else 3
    score += 8 if engagement else 2

    checks: dict[str, bool | str] = {
        "broad_topic": broad_topic,
        "strong_hook": strong_hook,
        "hook_type": hook_type,
        "value_proof": value_proof,
        "short_readable": short_readable,
        "visual_ready": visual_ready,
        "engagement": engagement,
    }
    return round(min(score, 100.0), 1), checks


def generate_threads_content_with_playbook(
    product: dict[str, Any],
    angle: str = "problem_solution",
    cta_keyword: str = "",
    count: int = 3,
    performance_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate more candidates, then re-rank them with the Threads playbook.

    The base content engine still owns product-evidence safety, hallucination
    filtering and AI generation. This layer only adds marketing construction
    scoring: broad topic, first-line hook, value proof, scannability, visual
    readiness and engagement potential.
    """
    requested = max(1, min(int(count), 5))
    expanded = max(requested, 5)
    rows = generate_threads_content(
        product,
        angle=angle,
        cta_keyword=cta_keyword,
        count=expanded,
        performance_context=performance_context,
    )

    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        playbook_score, checks = score_threads_playbook(
            str(item.get("body") or ""),
            product,
            str(item.get("image_url") or ""),
        )
        original_score = float(item.get("score") or 0.0)
        item["base_score"] = original_score
        item["playbook_score"] = playbook_score
        item["playbook_checks"] = checks
        item["hook_type"] = checks["hook_type"]
        item["score"] = round(original_score * 0.65 + playbook_score * 0.35, 1)
        enriched.append(item)

    enriched.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    return enriched[:requested]


__all__ = [
    "generate_threads_content_with_playbook",
    "score_threads_playbook",
]
