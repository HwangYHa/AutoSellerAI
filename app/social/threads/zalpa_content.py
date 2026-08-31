"""2026 Korean social tone layer for Threads commerce content.

The core content engine remains responsible for factual grounding, quality gates and
profit feedback. This module only changes conversational surface style so the copy
sounds native to current Korean Threads/Instagram usage instead of a shopping-mall
ad or an adult imitating slang.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from app.social.threads.content_engine import ANGLES, generate_threads_content as _generate_base


TONE_LABELS = {
    "zalpa": "2026 잘파/MZ 자연체",
    "casual": "자연스러운 20대 구어체",
    "clean": "담백한 소셜 판매형",
}

# Expressions that now read more like a dated meme template when mechanically
# inserted into commerce copy. They are not forbidden in human writing; the
# automation simply avoids manufacturing them.
_STALE_REPLACEMENTS = {
    "어쩔티비": "아니 이게 뭐임",
    "머선129": "이게 뭐지",
    "핵인싸": "요즘 감성",
    "중꺾마": "끝까지 보는 포인트",
}

_ZALPA_MARKERS = ("감다살", "이왜진", "ㄹㅇ", "걍", "은근", "ㅋㅋ", "영크크", "나만 아님")
_ZALPA_HOOKS = (
    "잠깐 이건 좀 감다살인데 ㅋㅋ",
    "아니 이런 포인트 은근 못 참음.",
    "ㄹㅇ 이런 건 한 번 더 보게 됨.",
    "이왜진… 별생각 없이 봤는데 은근 눈 감.",
    "약간 이런 거 취향 맞으면 바로 꽂히는 타입 아님?",
    "이런 데서 영크크 감성 갈리는 듯 ㅋㅋ",
)
_ZALPA_CTAS = (
    "더 궁금하면 댓글에 '{keyword}'만 툭. 핵심만 뽑아줄게.",
    "'{keyword}' 궁금한 사람 댓글 ㄱ. 필요한 것만 짧게 정리해봄.",
    "댓글에 '{keyword}' 남기면 알잘딱 핵심만 정리해줄게.",
    "궁금하면 '{keyword}'만 남겨. 길게 말고 포인트만 정리해줄게.",
)


def tone_label(value: str) -> str:
    return TONE_LABELS.get(value, TONE_LABELS["zalpa"])


def _pick(rows: tuple[str, ...], seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8", errors="ignore")).digest()
    return rows[int.from_bytes(digest[:4], "big") % len(rows)]


def _remove_stale_template_slang(text: str) -> str:
    result = text
    for old, new in _STALE_REPLACEMENTS.items():
        result = result.replace(old, new)
    return result


def _replace_existing_cta(paragraphs: list[str], keyword: str, replacement: str) -> list[str]:
    if not paragraphs:
        return [replacement]
    # The base generator intentionally puts the CTA in the final paragraph.
    # Replace it only when it looks like a CTA, avoiding accidental deletion of
    # product copy when a user's keyword is also a common product noun.
    last = paragraphs[-1]
    cta_markers = ("댓글", "남겨", "궁금", "키워드")
    if any(marker in last for marker in cta_markers) and (not keyword or keyword in last):
        paragraphs[-1] = replacement
    else:
        paragraphs.append(replacement)
    return paragraphs


def _fit_threads_limit(paragraphs: list[str], cta: str, limit: int = 500) -> str:
    text = "\n\n".join(x.strip() for x in paragraphs if x.strip()).strip()
    if len(text) <= limit:
        return text

    # Always preserve the final CTA instead of blindly slicing it away.
    body_parts = paragraphs[:-1] if paragraphs and paragraphs[-1] == cta else paragraphs
    budget = max(0, limit - len(cta) - 2)
    body = "\n\n".join(x.strip() for x in body_parts if x.strip())[:budget].rstrip(" .,!?:;·-\n")
    if body:
        return f"{body}\n\n{cta}"[:limit].strip()
    return cta[:limit].strip()


def style_threads_body(
    body: str,
    cta_keyword: str,
    *,
    tone: str = "zalpa",
    seed_context: str = "",
) -> str:
    """Apply a restrained current-Korean social tone without changing product facts."""
    text = _remove_stale_template_slang(str(body or "").strip())
    if not text or tone == "clean":
        return text[:500]

    paragraphs = [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]
    if not paragraphs:
        return text[:500]

    if tone == "casual":
        # Keep the grounded body mostly intact; just make the CTA less corporate.
        keyword = str(cta_keyword or "포인트").strip()
        cta = f"궁금하면 댓글에 '{keyword}'만 남겨. 필요한 것만 짧게 정리해줄게."
        paragraphs = _replace_existing_cta(paragraphs, keyword, cta)
        return _fit_threads_limit(paragraphs, cta)

    keyword = str(cta_keyword or "포인트").strip()
    seed = f"{seed_context}|{text}|{keyword}"
    if not any(marker in paragraphs[0] for marker in _ZALPA_MARKERS):
        paragraphs.insert(0, _pick(_ZALPA_HOOKS, seed))

    cta = _pick(_ZALPA_CTAS, seed + "|cta").format(keyword=keyword)
    paragraphs = _replace_existing_cta(paragraphs, keyword, cta)
    return _fit_threads_limit(paragraphs, cta)


def generate_threads_content(
    product: dict[str, Any],
    angle: str = "problem_solution",
    cta_keyword: str = "",
    count: int = 3,
    performance_context: dict[str, Any] | None = None,
    *,
    tone: str = "zalpa",
) -> list[dict[str, Any]]:
    """Generate grounded content, then apply the selected contemporary tone layer."""
    if tone not in TONE_LABELS:
        tone = "zalpa"
    rows = _generate_base(product, angle, cta_keyword, count, performance_context)
    seed_base = f"{product.get('id', '')}|{product.get('name', '')}|{angle}"
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        styled = dict(row)
        styled["body"] = style_threads_body(
            str(row.get("body") or ""),
            str(row.get("cta_keyword") or cta_keyword or ""),
            tone=tone,
            seed_context=f"{seed_base}|{index}",
        )
        styled["tone"] = tone
        styled["tone_label"] = tone_label(tone)
        styled["style_version"] = "kr-zalpha-2026.08"
        reason = str(row.get("reason") or "").strip()
        if tone == "zalpa":
            styled["reason"] = (reason + " · 최신 잘파/MZ 구어체 보정").strip(" ·")[:240]
        result.append(styled)
    return result


__all__ = ["ANGLES", "TONE_LABELS", "generate_threads_content", "style_threads_body", "tone_label"]
