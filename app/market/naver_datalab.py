"""네이버 데이터랩 트렌드 API + 쇼핑 검색 통계."""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class TrendPoint:
    period: str   # "2025-01-01"
    ratio: float  # 0–100 상대값


@dataclass
class ShoppingStats:
    total_items: int = 0
    avg_price: int = 0
    min_price: int = 0
    max_price: int = 0
    top_brands: list[str] = field(default_factory=list)
    sample_items: list[dict] = field(default_factory=list)  # [{name, price, mall}]


# ── 데이터랩 트렌드 ──────────────────────────────────────────────────────────────

def get_search_trend(keyword: str, months: int = 12) -> list[TrendPoint]:
    """데이터랩 키워드 트렌드 조회 (최근 N개월, 월별).

    데이터랩 미승인 앱이면 빈 리스트 반환 — 쇼핑 검색으로 대체 사용.
    """
    s = get_settings()
    client_id = s.naver_search_client_id
    client_secret = s.naver_search_client_secret
    if not client_id or not client_secret:
        return []

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=months * 31)

    body = {
        "startDate": start_dt.strftime("%Y-%m-%d"),
        "endDate": end_dt.strftime("%Y-%m-%d"),
        "timeUnit": "month",
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}],
    }
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.post(
            "https://openapi.naver.com/v1/datalab/search",
            headers=headers,
            json=body,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            points = data["results"][0]["data"]
            return [TrendPoint(p["period"][:7], round(p["ratio"], 1)) for p in points]
        logger.debug("DataLab %s: %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.warning("DataLab 트렌드 실패: %s", exc)

    return []


# ── 쇼핑 검색 통계 ────────────────────────────────────────────────────────────────

def get_shopping_stats(keyword: str, display: int = 100) -> ShoppingStats:
    """네이버 쇼핑 검색 API로 현황 수집 (상품 수·가격 범위·브랜드)."""
    s = get_settings()
    client_id = s.naver_search_client_id
    client_secret = s.naver_search_client_secret
    if not client_id or not client_secret:
        return ShoppingStats()

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {"query": keyword, "display": display, "sort": "sim"}

    try:
        resp = httpx.get(
            "https://openapi.naver.com/v1/search/shop.json",
            headers=headers,
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("쇼핑 검색 %s: %s", resp.status_code, resp.text[:80])
            return ShoppingStats()

        data = resp.json()
        items = data.get("items", [])
        total = data.get("total", 0)

        prices = [
            int(it["lprice"])
            for it in items
            if it.get("lprice") and int(it.get("lprice", 0)) > 0
        ]
        brands = list(dict.fromkeys(
            it.get("brand", "") for it in items if it.get("brand")
        ))[:6]
        samples = [
            {"name": it.get("title", "")[:40], "price": int(it.get("lprice", 0)),
             "mall": it.get("mallName", "")}
            for it in items[:10]
        ]

        return ShoppingStats(
            total_items=total,
            avg_price=int(sum(prices) / len(prices)) if prices else 0,
            min_price=min(prices) if prices else 0,
            max_price=max(prices) if prices else 0,
            top_brands=brands,
            sample_items=samples,
        )

    except Exception as exc:
        logger.warning("쇼핑 통계 실패: %s", exc)
        return ShoppingStats()
