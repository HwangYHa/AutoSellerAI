"""Claude AI 기반 시장 기회 점수 산출 (Opportunity Score)."""
from __future__ import annotations
import json
import logging
import re

from app.config import get_settings
from app.market.naver_datalab import TrendPoint, ShoppingStats
from app.market.coupang_best import CoupangBestItem

logger = logging.getLogger(__name__)


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────────

def calculate_opportunity_score(
    keyword: str,
    trend_data: list[TrendPoint],
    shopping_stats: ShoppingStats,
    coupang_best: list[CoupangBestItem],
) -> dict:
    """
    Returns:
        score          : int 0–100 종합 기회 점수
        breakdown      : {trend:int, competition:int, margin:int, demand:int}
        recommendation : str — 판매 전략 요약 (3–4문장)
        tags           : list[str] — 주요 특성 태그
        risk_factors   : list[str] — 주의 리스크
    """
    s = get_settings()
    if s.claude_api_key:
        result = _claude_score(keyword, trend_data, shopping_stats, coupang_best, s)
        if result:
            return result

    return _rule_based_score(keyword, trend_data, shopping_stats, coupang_best)


# ── Claude 분석 ───────────────────────────────────────────────────────────────────

def _claude_score(keyword, trend_data, shopping_stats, coupang_best, s) -> dict | None:
    prompt = f"""당신은 한국 이커머스 시장 전문 분석가입니다.
아래 데이터를 분석하여 "{keyword}" 키워드의 판매 기회 점수를 산출하세요.

[네이버 쇼핑 트렌드 (최근 12개월, 최대값=100 기준 상대값)]
{_fmt_trend(trend_data)}

[네이버 쇼핑 현황]
- 전체 상품 수: {shopping_stats.total_items:,}개
- 평균 가격: {shopping_stats.avg_price:,}원 (범위: {shopping_stats.min_price:,}~{shopping_stats.max_price:,}원)
- 주요 브랜드: {', '.join(shopping_stats.top_brands[:5]) or '파악 불가'}

[쿠팡 베스트셀러 상위 {len(coupang_best)}개]
{_fmt_best(coupang_best)}

[평가 기준 — 합계 100점]
- trend_score (0-30): 트렌드 상승/하락/안정세, 최근 3개월 방향성 및 계절성
- competition_score (0-25): 경쟁 강도 역수 (진입 여지: 상품 수 적고 리뷰 낮을수록 높음)
- margin_score (0-25): 마진 가능성 (가격 여유, 공급가 대비 소매가 차익 잠재력)
- demand_score (0-20): 수요 규모 (검색량, 리뷰 수, 트렌드 절대값)

JSON으로만 응답하세요 (마크다운 코드블록, 설명 없이 순수 JSON):
{{"score":75,"breakdown":{{"trend":22,"competition":18,"margin":20,"demand":15}},"recommendation":"판매 전략 3-4문장","tags":["상승트렌드","경쟁완화"],"risk_factors":["리스크1"]}}"""

    try:
        import anthropic
        model = getattr(s, "claude_model_heavy", None) or s.claude_model
        client = anthropic.Anthropic(api_key=s.claude_api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            _validate(data)
            return data
    except Exception as exc:
        logger.warning("Claude 기회점수 실패: %s", exc)

    return None


def _validate(data: dict) -> None:
    bd = data.get("breakdown", {})
    total = sum(bd.get(k, 0) for k in ("trend", "competition", "margin", "demand"))
    # score와 breakdown 합계가 크게 어긋나면 score를 합계로 교정
    if abs(data.get("score", 0) - total) > 5:
        data["score"] = total


# ── 규칙 기반 폴백 ─────────────────────────────────────────────────────────────────

def _rule_based_score(keyword, trend_data, shopping_stats, coupang_best) -> dict:
    # trend (0-30)
    if len(trend_data) >= 3:
        recent = trend_data[-3:]
        delta = recent[-1].ratio - recent[0].ratio
        trend_s = int(min(30, max(0, 15 + delta * 1.2)))
    else:
        trend_s = 14

    # competition (0-25): 상품 수 역비례
    n = shopping_stats.total_items
    comp_s = 25 if n < 200 else 20 if n < 2000 else 14 if n < 20000 else 8 if n < 100000 else 3

    # margin (0-25): 평균 가격 기준
    avg = shopping_stats.avg_price
    margin_s = 25 if avg > 50000 else 20 if avg > 20000 else 14 if avg > 8000 else 8 if avg > 3000 else 4

    # demand (0-20): 리뷰 평균
    if coupang_best:
        avg_reviews = sum(it.review_count for it in coupang_best) / len(coupang_best)
        demand_s = 20 if avg_reviews > 20000 else 16 if avg_reviews > 5000 else 12 if avg_reviews > 500 else 7
    else:
        demand_s = 8

    total = trend_s + comp_s + margin_s + demand_s

    tags = []
    if trend_s >= 20:
        tags.append("상승트렌드")
    elif trend_s <= 8:
        tags.append("하락주의")
    if comp_s >= 18:
        tags.append("블루오션")
    elif comp_s <= 6:
        tags.append("레드오션")
    if margin_s >= 20:
        tags.append("마진우수")
    if demand_s >= 16:
        tags.append("수요풍부")

    return {
        "score": total,
        "breakdown": {
            "trend": trend_s,
            "competition": comp_s,
            "margin": margin_s,
            "demand": demand_s,
        },
        "recommendation": (
            f"'{keyword}' 키워드 기회 점수 {total}점입니다. "
            f"네이버 쇼핑 등록 상품 수 {shopping_stats.total_items:,}개로 "
            f"{'진입 여지가 있습니다' if comp_s >= 15 else '경쟁이 치열합니다'}. "
            f"Claude API를 설정하면 심층 전략 분석이 제공됩니다."
        ),
        "tags": tags,
        "risk_factors": ["Claude API 미설정 — 규칙 기반 점수 (정확도 제한)"],
    }


# ── 포맷 헬퍼 ─────────────────────────────────────────────────────────────────────

def _fmt_trend(trend_data: list[TrendPoint]) -> str:
    if not trend_data:
        return "  (데이터랩 미설정 또는 권한 없음)"
    lines = [f"  {t.period}: {t.ratio}" for t in trend_data[-12:]]
    return "\n".join(lines)


def _fmt_best(items: list[CoupangBestItem]) -> str:
    if not items:
        return "  (수집 실패 또는 결과 없음)"
    lines = [
        f"  {it.rank}위: {it.name[:35]} | {it.price:,}원 | ★{it.rating} ({it.review_count:,}리뷰)"
        for it in items[:10]
    ]
    return "\n".join(lines)
