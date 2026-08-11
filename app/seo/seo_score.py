"""SEO 점수 산출 (100점 만점) — app/ai_scoring.py의 ScoreResult/가중치 구조를
동일한 스타일로 차용한 규칙 기반 엔진.

배점: 제목 20 / 키워드 20 / 설명 20 / 중복도 10 / CTR 15 / CVR 15
CTR/CVR은 app/db.py:ProductPerformance 최근 데이터를 사용하며, 데이터가 없으면
(신규 반영 직후 등) 중립값(만점의 절반)을 부여한다.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from app.db import ProductPerformance, get_db
from app.seo.duplicate_detector import find_duplicates
from app.seo.title_gen import _BANNED_WORDS

_TITLE_WEIGHT = 20.0
_KEYWORD_WEIGHT = 20.0
_DESC_WEIGHT = 20.0
_DUPLICATE_WEIGHT = 10.0
_CTR_WEIGHT = 15.0
_CVR_WEIGHT = 15.0

# 업계 평균 대비 벤치마크 (이 값 이상이면 만점)
_CTR_BENCHMARK = 0.03   # 3%
_CVR_BENCHMARK = 0.05   # 5%


@dataclass
class SeoScoreResult:
    total: float
    breakdown: dict = field(default_factory=dict)


def _title_score(name: str, category: str) -> float:
    if not name:
        return 0.0
    length = len(name)
    # 너무 짧으면(검색어 부족) 감점, 너무 길면(가독성 저하) 감점
    if 20 <= length <= 50:
        length_score = 100.0
    elif length < 20:
        length_score = max(0.0, length / 20 * 100)
    else:
        length_score = max(0.0, 100 - (length - 50) * 2)

    banned_penalty = 40.0 if any(w in name for w in _BANNED_WORDS) else 0.0
    category_bonus = 10.0 if category and category in name else 0.0

    return max(0.0, min(100.0, length_score - banned_penalty + category_bonus))


def _keyword_score(keywords: list[str], min_count: int) -> float:
    if not keywords:
        return 0.0
    ratio = len(keywords) / max(min_count, 1)
    return round(min(100.0, ratio * 100), 1)


def _description_score(detail_html: str) -> float:
    if not detail_html:
        return 0.0
    length = len(detail_html)
    length_score = min(100.0, length / 800 * 100)  # 800자 이상이면 만점
    has_structure = 20.0 if ("<li" in detail_html or "<h3" in detail_html) else 0.0
    return round(min(100.0, length_score * 0.8 + has_structure), 1)


def _duplicate_score(product_id: int) -> float:
    dupes = find_duplicates(product_id)
    return round(max(0.0, 100.0 - len(dupes) * 25), 1)


def _performance_scores(product_id: int, platform: str) -> tuple[float, float]:
    """최근 성과 스냅샷의 평균 CTR/CVR을 0~100 점수로 환산한다."""
    with get_db() as db:
        rows = (
            db.query(ProductPerformance)
            .filter_by(product_id=product_id, platform=platform)
            .order_by(ProductPerformance.snapshot_date.desc())
            .limit(30)
            .all()
        )
    if not rows:
        return 50.0, 50.0  # 데이터 없음 → 중립값

    avg_ctr = sum(r.ctr for r in rows) / len(rows)
    avg_cvr = sum(r.cvr for r in rows) / len(rows)
    ctr_score = round(min(100.0, avg_ctr / _CTR_BENCHMARK * 100), 1)
    cvr_score = round(min(100.0, avg_cvr / _CVR_BENCHMARK * 100), 1)
    return ctr_score, cvr_score


def score_seo(product_id: int, name: str, category: str, keywords: list[str],
             detail_html: str, platform: str, min_keywords: int = 30) -> SeoScoreResult:
    """상품의 현재(또는 제안된) 제목/키워드/설명에 대한 SEO 점수를 산출한다."""
    title_score = _title_score(name, category)
    keyword_score = _keyword_score(keywords, min_keywords)
    desc_score = _description_score(detail_html)
    dup_score = _duplicate_score(product_id)
    ctr_score, cvr_score = _performance_scores(product_id, platform)

    total = (
        title_score * _TITLE_WEIGHT
        + keyword_score * _KEYWORD_WEIGHT
        + desc_score * _DESC_WEIGHT
        + dup_score * _DUPLICATE_WEIGHT
        + ctr_score * _CTR_WEIGHT
        + cvr_score * _CVR_WEIGHT
    ) / 100.0

    return SeoScoreResult(
        total=round(min(100.0, max(0.0, total)), 1),
        breakdown={
            "title_score": title_score,
            "keyword_score": keyword_score,
            "description_score": desc_score,
            "duplicate_score": dup_score,
            "ctr_score": ctr_score,
            "cvr_score": cvr_score,
        },
    )
