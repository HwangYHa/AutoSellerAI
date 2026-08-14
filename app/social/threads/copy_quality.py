from __future__ import annotations

import re
from typing import Any


_ADULT_GENERIC_TERMS = {
    "성인용품", "여성용품", "여성자위기구", "남성자위기구", "자위기구",
    "딜도", "진동기", "바이브레이터", "바이브", "섹스토이",
}

_BAD_SALES_PATTERNS = (
    r"진입\s*장벽(?:이|가)?\s*낮",
    r"부담스럽지\s*않(?:은|다)",
    r"기본기에\s*충실",
    r"정품\s*여부만",
    r"괜찮은\s*선택(?:지)?",
    r"무난(?:한|할|하다)",
    r"제일\s*중요",
    r"안전성이\s*(?:제일|가장)\s*중요",
    r"원산지가\s*중국(?:이)?라도",
    r"처음\s*(?:도전|입문).*?(?:부담|장벽)",
    r"찾고\s*계신가요",
    r"구매할\s*때\s*무엇을\s*확인",
    r"상품\s*정보가\s*필요하면",
    r"Q\.\s*.*?A\.",
)

_SPEC_GAP_PATTERNS = (
    r"상세\s*스펙(?:\s*정보)?(?:가|이)?\s*(?:많지\s*않|부족|적|없)",
    r"스펙(?:이|가)?\s*(?:부족|적|없)",
    r"상세\s*정보(?:가|이)?\s*(?:많지\s*않|부족|적|없)",
    r"확인되는\s*정보만\s*보면",
    r"정보가\s*부족(?:해서|하니|하다)",
)

_FAKE_EXPERIENCE_PATTERNS = (
    r"내돈내산",
    r"내가\s*(?:직접\s*)?(?:샀|구매했|주문했)",
    r"직접\s*(?:사서|구매해서|주문해서|써봤|사용해봤)",
    r"(?:써|사용해)\s*보니",
    r"(?:며칠|일주일|한달|한\s*달)\s*(?:써|사용해)",
    r"배송\s*받(?:고|아|아서)",
    r"재구매",
)

_INTERNAL_TOKEN_RE = re.compile(r"\b(?:[A-Za-z]{2,}\d{3,}|\d{4,}[A-Za-z]{2,})\b")


def _tokens(text: str) -> list[str]:
    return [x for x in re.sub(r"[^0-9A-Za-z가-힣]+", " ", str(text or "")).split() if x]


def natural_product_name(verified: dict[str, Any]) -> str:
    """Turn supplier/SEO-stuffed titles into a human-facing brand/model name.

    This never invents a new name. It only removes known internal identifiers and
    trailing generic SEO terms. If the title cannot be safely shortened, it is kept.
    """
    raw = str(verified.get("name") or "").strip()
    if not raw:
        return "이 제품"

    internal = {
        str(verified.get("sku") or "").strip().lower(),
        str(verified.get("source_id") or "").strip().lower(),
    }
    parts = [p for p in raw.split() if p.lower() not in internal]
    if not parts:
        return raw

    first_generic = next((i for i, p in enumerate(parts) if p in _ADULT_GENERIC_TERMS), None)
    if first_generic is not None and first_generic >= 1:
        shortened = parts[:first_generic]
        if shortened:
            return " ".join(shortened[:5])

    if len(parts) > 1 and _INTERNAL_TOKEN_RE.fullmatch(parts[-1]):
        parts = parts[:-1]
    return " ".join(parts[:12]) or raw


def marketing_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Separate customer-facing evidence from internal operational metadata.

    Social copy should not volunteer origin/internal catalog facts unless another
    workflow explicitly requires them. They stay available in the source DB but are
    intentionally excluded from the creative prompt.
    """
    verified = dict(evidence.get("verified") or {})
    category = str(verified.get("category") or "").strip()
    public_category = "" if category.isdigit() else category
    name = natural_product_name(verified)

    public = {
        "display_name": name,
        "brand": verified.get("brand") or "",
        "category": public_category,
        "material": verified.get("material") or "",
        "sell_price": verified.get("sell_price"),
        "options": verified.get("options") or [],
        "stored_detail_text": verified.get("stored_detail_text") or "",
    }
    low_priority = {
        "source_url": verified.get("source_url") or "",
    }
    internal = {
        "sku": verified.get("sku") or "",
        "source": verified.get("source") or "",
        "source_id": verified.get("source_id") or "",
        "raw_category": category,
        "origin": verified.get("origin") or "",
        "supply_price": verified.get("supply_price"),
        "status": verified.get("status") or "",
    }
    return {
        "public_facts": public,
        "low_priority_facts": low_priority,
        "never_expose": internal,
        "supplemental_source_page_text": evidence.get("supplemental_source_page_text") or "",
        "evidence_stats": evidence.get("evidence_stats") or {},
    }


def copy_quality_issues(body: str, evidence: dict[str, Any], cta_keyword: str = "") -> list[str]:
    text = str(body or "").strip()
    issues: list[str] = []
    verified = evidence.get("verified") or {}

    if not text:
        return ["empty"]
    if len(text) > 500:
        issues.append("too_long")

    for key in ("sku", "source_id"):
        value = str(verified.get(key) or "").strip()
        if value and value.lower() in text.lower():
            issues.append(f"internal_{key}")

    category = str(verified.get("category") or "").strip()
    if category.isdigit() and re.search(rf"(?<!\d){re.escape(category)}(?!\d)", text):
        issues.append("numeric_category")

    origin = str(verified.get("origin") or "").strip()
    if origin and re.search(rf"(?<![0-9A-Za-z가-힣]){re.escape(origin)}(?:산|\s*제품)?(?![0-9A-Za-z가-힣])", text):
        issues.append("origin_overexposure")

    if _INTERNAL_TOKEN_RE.search(text):
        known_internal = {
            str(verified.get("sku") or "").lower(),
            str(verified.get("source_id") or "").lower(),
        }
        found = {x.lower() for x in _INTERNAL_TOKEN_RE.findall(text)}
        if found & known_internal:
            issues.append("internal_code")

    for pattern in _BAD_SALES_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            issues.append("unsupported_or_template_judgment")
            break

    for pattern in _SPEC_GAP_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            issues.append("spec_gap_disclaimer")
            break

    for pattern in _FAKE_EXPERIENCE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            issues.append("fabricated_personal_experience")
            break

    adult_term_hits = sum(1 for term in _ADULT_GENERIC_TERMS if term in text)
    if adult_term_hits >= 4:
        issues.append("keyword_stuffing")

    if cta_keyword:
        count = text.count(cta_keyword)
        if count == 0:
            issues.append("missing_cta")
        elif count > 1:
            issues.append("duplicate_cta")

    if len(re.findall(r"(?:입니다|하세요|계신가요|필요합니다)(?:\.|$)", text)) >= 2:
        issues.append("formal_ad_tone")

    return sorted(set(issues))


def sales_copy_score(body: str, evidence: dict[str, Any], cta_keyword: str = "") -> tuple[float, list[str]]:
    issues = copy_quality_issues(body, evidence, cta_keyword)
    score = 100.0
    weights = {
        "empty": 100,
        "internal_sku": 45,
        "internal_source_id": 45,
        "internal_code": 40,
        "numeric_category": 35,
        "keyword_stuffing": 35,
        "unsupported_or_template_judgment": 30,
        "origin_overexposure": 30,
        "spec_gap_disclaimer": 35,
        "fabricated_personal_experience": 45,
        "formal_ad_tone": 15,
        "missing_cta": 15,
        "duplicate_cta": 12,
        "too_long": 10,
    }
    for issue in issues:
        score -= weights.get(issue, 10)

    paragraphs = [x.strip() for x in re.split(r"\n\s*\n", str(body or "")) if x.strip()]
    if 3 <= len(paragraphs) <= 6:
        score += 5
    return max(0.0, min(score, 100.0)), issues
