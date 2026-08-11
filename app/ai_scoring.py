"""AI 상품 선별 엔진 (Layer 3).

[설계 원칙]
  - 공급사마다 판매 성공에 영향을 미치는 요소가 다름
  - 도매꾹: MOQ·배송비·마진 중심
  - 도매매: 재고안정성·발주성공률·마진 중심
  - 온채널: 공급사신뢰도·출고속도·품절률·마진 중심
  - Claude 가용 시 룰 점수 상위 30개를 AI 재점수로 보정

[점수 구조 - 100점 만점]
  각 공급사별 차원 × 가중치 → 합산 (0~100)

[필터 기준]
  min_score=80 → 상위 20% 선별
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.suppliers.base import NormalizedProduct

logger = logging.getLogger(__name__)

# ── 공급사별 점수 차원 정의 ──────────────────────────────────────────────────────

@dataclass
class ScoreResult:
    total: float               # 0~100 최종 점수
    breakdown: dict            # 차원별 점수
    passed: bool               # min_score 통과 여부
    reject_reason: str = ""    # 탈락 사유


# 공급사별 평가 차원 × 가중치
_WEIGHTS: dict[str, dict[str, float]] = {
    "domeggook": {
        "moq_score":        0.30,   # MOQ=1 여부 (핵심)
        "shipping_score":   0.20,   # 배송비 경쟁력
        "margin_score":     0.50,   # 마진율
    },
    "domemai": {
        "stock_stability":  0.35,   # 재고 안정성
        "fulfillment_rate": 0.30,   # 발주 성공률
        "margin_score":     0.35,   # 마진율
    },
    "onchannel": {
        "reliability":          0.25,   # 공급사 신뢰도
        "lead_time_score":      0.20,   # 출고 속도
        "stockout_score":       0.20,   # 품절률 (낮을수록 좋음 → 역수 변환)
        "margin_score":         0.25,   # 마진율
        "approval_success":     0.10,   # 승인 성공률 (온채널 전용)
    },
    "default": {
        "margin_score":     0.40,
        "stock_stability":  0.30,
        "price_range":      0.20,
        "image_score":      0.10,
    },
}

# 하드 필터 기준 — 이 조건 미충족 시 즉시 탈락 (점수 계산 전)
HARD_FILTERS = {
    "moq_max":        1,        # MOQ 1 초과 시 탈락
    "min_price":      3000,     # 원가 3000원 미만 탈락
    "min_stock":      0,        # 재고 0 허용 (무한재고 가능)
    "max_lead_time":  7,        # 출고 7일 초과 탈락
}


def score_product(
    product: NormalizedProduct,
    target_margin: float = 0.25,
    fee_rate: float = 0.108,
    shipping_cost: float = 3000.0,
) -> ScoreResult:
    """단일 NormalizedProduct에 대해 공급사 특화 점수를 계산한다."""

    # ── 1. 하드 필터 ─────────────────────────────────────────────────────────
    if product.moq > HARD_FILTERS["moq_max"]:
        return ScoreResult(0, {}, False, f"MOQ={product.moq} > 1")
    if product.supply_price < HARD_FILTERS["min_price"]:
        return ScoreResult(0, {}, False, f"공급가 {product.supply_price}원 < 최소기준")
    if product.lead_time_days > HARD_FILTERS["max_lead_time"]:
        return ScoreResult(0, {}, False, f"출고일 {product.lead_time_days}일 > 7일")

    # ── 2. 마진율 계산 ────────────────────────────────────────────────────────
    sell = product.supply_price * 3.5
    margin = (sell - product.supply_price - shipping_cost - sell * fee_rate) / sell
    if margin < 0:
        return ScoreResult(0, {}, False, f"마진율 음수: {margin:.1%}")

    weights = _WEIGHTS.get(product.supplier_id, _WEIGHTS["default"])
    breakdown: dict[str, float] = {}
    total = 0.0

    # ── 3. 공급사별 차원 점수 계산 ────────────────────────────────────────────

    if product.supplier_id == "domeggook":
        # MOQ 점수: MOQ=1이면 100, 아니면 0 (도매꾹 핵심 지표)
        moq_score = 100.0 if product.moq == 1 else 0.0
        # 배송비 점수: 2500원 이하 100점, 5000원 이상 0점
        ship_score = max(0, 100 - (product.shipping_fee - 2500) / 25)
        # 마진 점수
        margin_score = _margin_to_score(margin, target_margin)

        breakdown = {
            "moq_score": round(moq_score, 1),
            "shipping_score": round(ship_score, 1),
            "margin_score": round(margin_score, 1),
        }
        total = (moq_score * weights["moq_score"]
                 + ship_score * weights["shipping_score"]
                 + margin_score * weights["margin_score"])

    elif product.supplier_id == "domemai":
        # 재고 안정성: stock >= 100이면 100, 30이면 50, 0이면 80 (무한재고 추정)
        if product.stock == 0:
            stock_score = 80.0
        else:
            stock_score = min(100.0, product.stock * 1.0)
        # 발주 성공률: 0~1 → 0~100
        fulfill_score = product.fulfillment_rate * 100
        margin_score = _margin_to_score(margin, target_margin)

        breakdown = {
            "stock_stability": round(stock_score, 1),
            "fulfillment_rate": round(fulfill_score, 1),
            "margin_score": round(margin_score, 1),
        }
        total = (stock_score * weights["stock_stability"]
                 + fulfill_score * weights["fulfillment_rate"]
                 + margin_score * weights["margin_score"])

    elif product.supplier_id == "onchannel":
        # 공급사 신뢰도: 0~1 → 0~100
        rel_score = product.supplier_reliability * 100
        # 출고 속도: 1일=100, 3일=70, 7일=0
        lead_score = max(0, 100 - (product.lead_time_days - 1) * 15)
        # 품절률: 낮을수록 좋음 (0% = 100점, 20% = 0점)
        stockout_score = max(0, 100 - product.stockout_rate * 500)
        margin_score = _margin_to_score(margin, target_margin)
        # 승인 성공률: raw_data에 저장된 실적 또는 카테고리 추정값 사용
        approval_rate = product.raw_data.get("approval_success_rate", 0.75)
        approval_score = approval_rate * 100

        breakdown = {
            "reliability": round(rel_score, 1),
            "lead_time_score": round(lead_score, 1),
            "stockout_score": round(stockout_score, 1),
            "margin_score": round(margin_score, 1),
            "approval_success": round(approval_score, 1),
        }
        total = (rel_score * weights["reliability"]
                 + lead_score * weights["lead_time_score"]
                 + stockout_score * weights["stockout_score"]
                 + margin_score * weights["margin_score"]
                 + approval_score * weights["approval_success"])

    else:
        # 기본 공급사
        margin_score = _margin_to_score(margin, target_margin)
        stock_score = 80.0 if product.stock == 0 else min(100.0, product.stock)
        price_score = _price_range_score(product.supply_price)
        img_score = 100.0 if product.images else 0.0

        breakdown = {
            "margin_score": round(margin_score, 1),
            "stock_stability": round(stock_score, 1),
            "price_range": round(price_score, 1),
            "image_score": round(img_score, 1),
        }
        total = (margin_score * weights["margin_score"]
                 + stock_score * weights["stock_stability"]
                 + price_score * weights["price_range"]
                 + img_score * weights["image_score"])

    total = min(100.0, max(0.0, total))

    return ScoreResult(
        total=round(total, 1),
        breakdown=breakdown,
        passed=total >= 0,  # 하드필터 통과 = 점수 계산 완료
        reject_reason="",
    )


def score_products(
    products: list[NormalizedProduct],
    min_score: float = 80.0,
    target_margin: float = 0.25,
    fee_rate: float = 0.108,
    shipping_cost: float = 3000.0,
    apply_claude: bool = True,
    keywords: list[str] | None = None,
) -> list[tuple[NormalizedProduct, ScoreResult]]:
    """상품 목록 전체에 점수를 계산하고 min_score 이상만 반환한다.

    Returns: [(product, score_result), ...] — 점수 내림차순
    """
    scored: list[tuple[NormalizedProduct, ScoreResult]] = []

    for p in products:
        result = score_product(p, target_margin, fee_rate, shipping_cost)
        scored.append((p, result))

    # Claude 재점수 (상위 30개 대상)
    if apply_claude and keywords:
        _apply_claude_rescore(scored, keywords, top_n=30)

    # 정렬 후 min_score 필터
    scored.sort(key=lambda x: x[1].total, reverse=True)
    return [(p, r) for p, r in scored if r.total >= min_score]


def _apply_claude_rescore(
    scored: list[tuple[NormalizedProduct, ScoreResult]],
    keywords: list[str],
    top_n: int = 30,
) -> None:
    """Claude API로 상위 n개 상품 점수를 재보정한다 (in-place)."""
    from app.config import get_settings
    s = get_settings()
    if not s.claude_api_key:
        return

    top = sorted(scored, key=lambda x: x[1].total, reverse=True)[:top_n]
    prod_list = "\n".join(
        f"{i+1}. [{p.supplier_id}] {p.name[:40]} / "
        f"원가:{p.supply_price:,.0f}원 / MOQ:{p.moq} / 재고:{p.stock} / "
        f"출고:{p.lead_time_days}일"
        for i, (p, _) in enumerate(top)
    )

    try:
        import anthropic, json as _json, re
        client = anthropic.Anthropic(api_key=s.claude_api_key)
        msg = client.messages.create(
            model=s.claude_model,
            max_tokens=1200,
            messages=[{"role": "user", "content": f"""
한국 이커머스 전문 MD 역할입니다.
아래 {len(top)}개 도매 상품의 실제 판매 가능성을 0-100점으로 평가하세요.
검색 트렌드 키워드: {', '.join(keywords[:3])}

평가 기준:
- 시장 수요 및 검색 트렌드 매칭 (40점)
- 경쟁 강도 및 차별성 (30점)
- 상품 특성 (MOQ, 재고, 출고일) (30점)

{prod_list}

JSON 배열로만 응답 (다른 텍스트 없이):
[{{"idx":1,"score":85,"reason":"트렌드 일치"}},...]
"""}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if not m:
            return

        ai_scores = _json.loads(m.group())
        score_map = {int(d["idx"]): float(d["score"])
                     for d in ai_scores if "idx" in d and "score" in d}

        for i, (p, r) in enumerate(top):
            if i + 1 in score_map:
                ai_val = score_map[i + 1]
                # AI 점수와 룰 점수 블렌딩 (60% AI + 40% 룰)
                blended = round(ai_val * 0.6 + r.total * 0.4, 1)
                r.total = min(100.0, blended)
                r.breakdown["ai_rescore"] = ai_val

    except Exception as exc:
        logger.warning("Claude 재점수 실패 (룰 점수 유지): %s", exc)


def _margin_to_score(margin: float, target: float) -> float:
    """마진율을 0-100 점수로 변환."""
    if margin >= target * 2:     return 100.0
    if margin >= target * 1.5:   return 85.0
    if margin >= target:          return 70.0
    if margin >= target * 0.8:   return 50.0
    if margin >= target * 0.5:   return 30.0
    return max(0.0, margin / target * 30)


def _price_range_score(supply_price: float) -> float:
    """1만~5만원 적정 가격대 점수."""
    if 10000 <= supply_price <= 50000:  return 100.0
    if 5000 <= supply_price < 10000:    return 75.0
    if 50000 < supply_price <= 100000:  return 60.0
    if 3000 <= supply_price < 5000:     return 50.0
    return 20.0
