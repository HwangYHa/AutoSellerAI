"""AI 상품 랭킹 엔진 (Product Ranking Engine).

[목표]
  도매꾹·도매매·온채널 합산 수십만 상품 중 상위 5%만 선별
  → 3만 선별 → 3000개 등록 → 300개 주력 → 30개 효자상품

[평가 6개 차원]
  1. 검색량 점수    (25%) — 시장 수요
  2. 경쟁 강도      (20%) — 낮을수록 좋음
  3. 리뷰 증가율    (10%) — 성장하는 카테고리
  4. 마진 점수      (25%) — 수익성
  5. 배송 속도      (10%) — 고객 만족도
  6. 품절률         (10%) — 운영 안정성

[Claude 보정]
  상위 50개 대상으로 트렌드·계절성·경쟁구도 분석 → 60%AI + 40%룰 블렌딩
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.suppliers.base import NormalizedProduct

logger = logging.getLogger(__name__)


@dataclass
class RankingScore:
    total: float                    # 0~100 최종 랭킹 점수
    breakdown: dict                 # 차원별 점수
    rank_tier: str                  # TOP5 / TOP10 / TOP20 / REST
    recommendation: str = ""        # AI 추천 코멘트


# 랭킹 차원 가중치
_RANKING_WEIGHTS = {
    "search_demand":    0.25,   # 검색량/시장 수요
    "competition":      0.20,   # 경쟁 강도 (낮을수록 높은 점수)
    "review_growth":    0.10,   # 리뷰 증가율
    "margin":           0.25,   # 마진율
    "shipping_speed":   0.10,   # 배송 속도
    "stockout_safety":  0.10,   # 품절 안전성 (낮을수록 높은 점수)
}


def rank_product(
    product: NormalizedProduct,
    keyword_search_volume: int = 0,
    competitor_count: int = 0,
    review_growth_rate: float = 0.0,
    target_margin: float = 0.25,
    fee_rate: float = 0.108,
    shipping_cost: float = 3000.0,
) -> RankingScore:
    """단일 상품의 랭킹 점수를 계산한다."""

    # 1. 검색량 점수: 월 10만 이상 = 100점
    if keyword_search_volume >= 100000:
        demand_score = 100.0
    elif keyword_search_volume >= 50000:
        demand_score = 85.0
    elif keyword_search_volume >= 10000:
        demand_score = 70.0
    elif keyword_search_volume >= 3000:
        demand_score = 50.0
    elif keyword_search_volume > 0:
        demand_score = 30.0
    else:
        # 검색량 데이터 없음 → 카테고리 기반 추정
        demand_score = _estimate_demand_from_category(product.category)

    # 2. 경쟁 강도 점수: 경쟁자 적을수록 높음
    if competitor_count == 0:
        competition_score = 70.0  # 데이터 없음 → 중간값
    elif competitor_count <= 50:
        competition_score = 100.0
    elif competitor_count <= 200:
        competition_score = 80.0
    elif competitor_count <= 1000:
        competition_score = 60.0
    elif competitor_count <= 5000:
        competition_score = 40.0
    else:
        competition_score = 20.0

    # 3. 리뷰 증가율: 월 10% 이상 = 100점
    if review_growth_rate >= 0.10:
        review_score = 100.0
    elif review_growth_rate >= 0.05:
        review_score = 70.0
    elif review_growth_rate >= 0.02:
        review_score = 50.0
    elif review_growth_rate > 0:
        review_score = 30.0
    else:
        review_score = 40.0  # 데이터 없음 → 기본값

    # 4. 마진 점수
    sell = product.supply_price * 3.5
    margin = (sell - product.supply_price - shipping_cost - sell * fee_rate) / sell
    margin = max(0.0, margin)
    if margin >= target_margin * 2:     margin_score = 100.0
    elif margin >= target_margin * 1.5: margin_score = 85.0
    elif margin >= target_margin:       margin_score = 70.0
    elif margin >= target_margin * 0.8: margin_score = 50.0
    else:                               margin_score = max(0.0, margin / target_margin * 50)

    # 5. 배송 속도: 1일=100, 7일=0
    ship_score = max(0.0, 100.0 - (product.lead_time_days - 1) * 16.5)

    # 6. 품절 안전성: 낮은 품절률 = 높은 점수
    stockout_score = max(0.0, 100.0 - product.stockout_rate * 500)

    breakdown = {
        "search_demand":   round(demand_score, 1),
        "competition":     round(competition_score, 1),
        "review_growth":   round(review_score, 1),
        "margin":          round(margin_score, 1),
        "shipping_speed":  round(ship_score, 1),
        "stockout_safety": round(stockout_score, 1),
        "calc_margin_pct": round(margin * 100, 1),
    }

    total = (
        demand_score    * _RANKING_WEIGHTS["search_demand"]
        + competition_score * _RANKING_WEIGHTS["competition"]
        + review_score  * _RANKING_WEIGHTS["review_growth"]
        + margin_score  * _RANKING_WEIGHTS["margin"]
        + ship_score    * _RANKING_WEIGHTS["shipping_speed"]
        + stockout_score * _RANKING_WEIGHTS["stockout_safety"]
    )
    total = min(100.0, max(0.0, total))

    tier = _score_to_tier(total)

    return RankingScore(
        total=round(total, 1),
        breakdown=breakdown,
        rank_tier=tier,
    )


def rank_products(
    products: list[NormalizedProduct],
    top_pct: float = 0.05,
    keyword_data: dict | None = None,
    apply_claude: bool = True,
    keywords: list[str] | None = None,
) -> list[tuple[NormalizedProduct, RankingScore]]:
    """상품 목록 전체 랭킹 계산 → 상위 top_pct(기본 5%)만 반환.

    keyword_data: {"product_raw_id": {"search_volume": int, "competitor_count": int, ...}}
    """
    scored: list[tuple[NormalizedProduct, RankingScore]] = []

    for p in products:
        kd = (keyword_data or {}).get(p.raw_id, {})
        rs = rank_product(
            p,
            keyword_search_volume=kd.get("search_volume", 0),
            competitor_count=kd.get("competitor_count", 0),
            review_growth_rate=kd.get("review_growth_rate", 0.0),
        )
        scored.append((p, rs))

    # Claude 보정: 상위 50개 대상
    if apply_claude and keywords:
        _apply_claude_ranking_boost(scored, keywords, top_n=50)

    scored.sort(key=lambda x: x[1].total, reverse=True)

    # 상위 top_pct만 반환
    cutoff = max(1, int(len(scored) * top_pct))
    top = scored[:cutoff]

    # 상대적 티어 재계산
    for i, (p, rs) in enumerate(top):
        pct_rank = i / max(len(top), 1)
        rs.rank_tier = "TOP5" if pct_rank < 0.05 else \
                       "TOP10" if pct_rank < 0.10 else \
                       "TOP20" if pct_rank < 0.20 else "REST"

    logger.info("랭킹 계산 완료: 전체 %d개 → 상위 %d개 (%.0f%%)",
                len(products), len(top), top_pct * 100)
    return top


def _apply_claude_ranking_boost(
    scored: list[tuple[NormalizedProduct, RankingScore]],
    keywords: list[str],
    top_n: int = 50,
) -> None:
    """Claude로 상위 top_n개의 트렌드·계절성·경쟁구도를 평가해 점수를 보정한다 (in-place)."""
    from app.config import get_settings
    s = get_settings()
    if not s.claude_api_key:
        return

    top = sorted(scored, key=lambda x: x[1].total, reverse=True)[:top_n]
    prod_list = "\n".join(
        f"{i+1}. [{p.supplier_id}] {p.name[:40]} "
        f"/ 원가:{p.supply_price:,.0f}원 / 마진:{rs.breakdown.get('calc_margin_pct', 0):.1f}%"
        for i, (p, rs) in enumerate(top)
    )

    try:
        import anthropic, json as _json, re as _re
        client = anthropic.Anthropic(api_key=s.claude_api_key)
        msg = client.messages.create(
            model=s.claude_model,
            max_tokens=1500,
            messages=[{"role": "user", "content": f"""
한국 이커머스 시장 전문 MD 역할입니다.
아래 {len(top)}개 도매 상품의 실제 판매 잠재력을 0-100점으로 평가하세요.

검색 트렌드 키워드: {', '.join((keywords or [])[:3])}

평가 기준 (각 항목 중요도 순):
1. 현재 쿠팡·네이버 트렌드 키워드와의 매칭도 (35점)
2. 계절성·특수 이벤트 수혜 가능성 (20점)
3. 차별화 포인트 및 경쟁 우위 (25점)
4. 재구매율·충성도 가능성 (20점)

상품 목록:
{prod_list}

JSON 배열로만 응답 (설명 없이):
[{{"idx":1,"score":85,"reason":"트렌드 일치 높음"}},...]
"""}],
        )
        text = msg.content[0].text.strip()
        m = _re.search(r'\[.*\]', text, _re.DOTALL)
        if not m:
            return

        ai_scores = _json.loads(m.group())
        score_map = {int(d["idx"]): (float(d["score"]), d.get("reason", ""))
                     for d in ai_scores if "idx" in d and "score" in d}

        for i, (p, rs) in enumerate(top):
            if i + 1 in score_map:
                ai_val, reason = score_map[i + 1]
                blended = round(ai_val * 0.6 + rs.total * 0.4, 1)
                rs.total = min(100.0, blended)
                rs.breakdown["ai_ranking_score"] = ai_val
                if reason:
                    rs.recommendation = reason[:100]

    except Exception as exc:
        logger.warning("Claude 랭킹 보정 실패 (룰 점수 유지): %s", exc)


def _score_to_tier(score: float) -> str:
    if score >= 90: return "TOP5"
    if score >= 80: return "TOP10"
    if score >= 70: return "TOP20"
    return "REST"


def _estimate_demand_from_category(category: str) -> float:
    """카테고리명으로 수요를 추정한다."""
    high_demand = ["주방", "생활", "뷰티", "건강", "스포츠", "반려"]
    mid_demand  = ["패션", "의류", "전자", "완구", "도서"]
    low_demand  = ["산업", "의료", "농업"]

    cat = category or ""
    for kw in high_demand:
        if kw in cat:
            return 70.0
    for kw in mid_demand:
        if kw in cat:
            return 55.0
    for kw in low_demand:
        if kw in cat:
            return 30.0
    return 50.0
