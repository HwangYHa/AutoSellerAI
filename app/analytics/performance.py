"""상품 생존율 엔진 (Product Survival Rate Engine).

[설계 원칙]
  - "많이 등록"이 아닌 "잘 팔리는 상품만 유지" 전략의 핵심 모듈
  - 7일·14일·30일 윈도우별로 성과를 판정
  - 기준 미달 상품은 자동 삭제 후보로 분류 → 교체 파이프라인 트리거

[판정 기준]
  노출 500+ & 클릭률 < 0.5% → DELETE_CANDIDATE (노출은 되지만 클릭 없음)
  노출 500+ & 클릭률 >= 0.5% & 전환률 < 1%  → WATCH (클릭은 되지만 구매 없음)
  노출 500+ & 클릭률 >= 0.5% & 전환률 >= 1% → HEALTHY
  노출 < 500 (7일) → WATCH (노출 부족 — 제목/이미지 개선 고려)

  생존 점수(0~100):
    노출점수 × 30% + CTR점수 × 35% + CVR점수 × 35%
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)


# ── 생존 판정 기준 ─────────────────────────────────────────────────────────────

@dataclass
class SurvivalThreshold:
    window_days: int
    min_impressions: int    # 이 이하면 노출 부족 판정
    min_ctr: float          # 최소 클릭률 (0~1)
    min_cvr: float          # 최소 전환률 (0~1)


THRESHOLDS = {
    7:  SurvivalThreshold(7,  min_impressions=200, min_ctr=0.005, min_cvr=0.01),
    14: SurvivalThreshold(14, min_impressions=400, min_ctr=0.005, min_cvr=0.01),
    30: SurvivalThreshold(30, min_impressions=800, min_ctr=0.008, min_cvr=0.015),
}

STATUS_HEALTHY  = "HEALTHY"
STATUS_WATCH    = "WATCH"
STATUS_DELETE   = "DELETE_CANDIDATE"
STATUS_DELETED  = "DELETED"


# ── 성과 데이터 수집 ───────────────────────────────────────────────────────────

def collect_performance(platform: str = "all", days_back: int = 1) -> dict:
    """플랫폼 광고/판매 통계 API에서 성과 데이터를 수집해 DB에 저장한다.

    현재는 플랫폼 API가 광고 노출 데이터를 제공하지 않으므로
    판매 주문 데이터(ProductPerformance.orders·revenue)만 채우고
    impressions/clicks는 0으로 저장한다 (광고 API 연동 시 업데이트).
    """
    from app.db import get_db, ProductPerformance, Listing, Order, Product

    today_str = date.today().isoformat()
    since = datetime.utcnow() - timedelta(days=days_back)
    stats = {"inserted": 0, "platforms": []}

    platforms = (["coupang", "smartstore"] if platform == "all"
                 else [platform])

    with get_db() as db:
        for plat in platforms:
            # 등록 성공한 상품 목록
            listings = db.query(Listing).filter_by(
                platform=plat, status="success"
            ).all()

            for lst in listings:
                # 최근 days_back 일 주문 집계
                orders = db.query(Order).filter(
                    Order.product_id == lst.product_id,
                    Order.platform == plat,
                    Order.created_at >= since,
                ).all()

                order_count = sum(o.quantity for o in orders)
                revenue = sum(o.gross_revenue for o in orders)

                # 등록일 이후 전체 누적
                all_orders = db.query(Order).filter_by(
                    product_id=lst.product_id, platform=plat
                ).all()
                cum_orders = sum(o.quantity for o in all_orders)
                cum_revenue = sum(o.gross_revenue for o in all_orders)

                # 상품 등록일 계산
                product = db.query(Product).filter_by(id=lst.product_id).first()
                listed_dt = lst.created_at if lst.created_at else datetime.utcnow()
                days_listed = max(1, (datetime.utcnow() - listed_dt).days)

                perf = ProductPerformance(
                    product_id=lst.product_id,
                    listing_id=lst.id,
                    platform=plat,
                    platform_product_id=lst.platform_id,
                    snapshot_date=today_str,
                    days_since_listed=days_listed,
                    impressions=0,      # 광고 API 연동 전 미수집
                    clicks=0,
                    orders=order_count,
                    revenue=revenue,
                    ctr=0.0,
                    cvr=0.0,
                    cum_impressions=0,
                    cum_clicks=0,
                    cum_orders=cum_orders,
                    cum_revenue=cum_revenue,
                )
                db.add(perf)
                stats["inserted"] += 1

            db.commit()
            stats["platforms"].append(plat)

    logger.info("성과 데이터 수집 완료: %s", stats)
    return stats


def ingest_ad_performance(platform: str, rows: list[dict]) -> dict:
    """외부 광고 API 응답을 ProductPerformance에 적재한다.

    rows 형식:
      [{"platform_product_id": str, "date": "YYYY-MM-DD",
        "impressions": int, "clicks": int, "orders": int, "revenue": float}]
    """
    from app.db import get_db, ProductPerformance, Listing

    inserted = updated = 0

    with get_db() as db:
        for row in rows:
            pid = row.get("platform_product_id", "")
            snap_date = row.get("date", date.today().isoformat())

            listing = db.query(Listing).filter_by(
                platform=platform, platform_id=pid, status="success"
            ).first()
            if not listing:
                continue

            existing = db.query(ProductPerformance).filter_by(
                product_id=listing.product_id,
                platform=platform,
                snapshot_date=snap_date,
            ).first()

            impr = int(row.get("impressions", 0))
            clks = int(row.get("clicks", 0))
            ords = int(row.get("orders", 0))
            rev = float(row.get("revenue", 0.0))
            ctr = clks / impr if impr > 0 else 0.0
            cvr = ords / clks if clks > 0 else 0.0

            if existing:
                existing.impressions = impr
                existing.clicks = clks
                existing.orders = ords
                existing.revenue = rev
                existing.ctr = round(ctr, 5)
                existing.cvr = round(cvr, 5)
                updated += 1
            else:
                db.add(ProductPerformance(
                    product_id=listing.product_id,
                    listing_id=listing.id,
                    platform=platform,
                    platform_product_id=pid,
                    snapshot_date=snap_date,
                    impressions=impr, clicks=clks, orders=ords, revenue=rev,
                    ctr=round(ctr, 5), cvr=round(cvr, 5),
                ))
                inserted += 1

        db.commit()

    return {"inserted": inserted, "updated": updated}


# ── 생존율 분석 ────────────────────────────────────────────────────────────────

def run_survival_analysis(window_days: int = 7,
                          platform: str = "all") -> list[dict]:
    """등록 상품에 대해 window_days 기간 성과를 집계하고 생존 여부를 판정한다.

    Returns: 판정된 상품 목록 [{"product_id", "status", "survival_score", ...}]
    """
    from app.db import get_db, ProductPerformance, ProductSurvivalStatus, Listing
    from sqlalchemy import func

    today_str = date.today().isoformat()
    since_str = (date.today() - timedelta(days=window_days)).isoformat()
    threshold = THRESHOLDS.get(window_days, THRESHOLDS[7])
    platforms = ["coupang", "smartstore"] if platform == "all" else [platform]
    results = []

    with get_db() as db:
        for plat in platforms:
            listings = db.query(Listing).filter_by(
                platform=plat, status="success"
            ).all()

            for lst in listings:
                # window_days 기간 집계
                rows = db.query(
                    func.sum(ProductPerformance.impressions).label("impr"),
                    func.sum(ProductPerformance.clicks).label("clks"),
                    func.sum(ProductPerformance.orders).label("ords"),
                    func.sum(ProductPerformance.revenue).label("rev"),
                ).filter(
                    ProductPerformance.product_id == lst.product_id,
                    ProductPerformance.platform == plat,
                    ProductPerformance.snapshot_date >= since_str,
                    ProductPerformance.snapshot_date <= today_str,
                ).first()

                impr = int(rows.impr or 0)
                clks = int(rows.clks or 0)
                ords = int(rows.ords or 0)
                rev = float(rows.rev or 0.0)
                ctr = clks / impr if impr > 0 else 0.0
                cvr = ords / clks if clks > 0 else 0.0

                listed_dt = lst.created_at if lst.created_at else datetime.utcnow()
                days_listed = max(1, (datetime.utcnow() - listed_dt).days)

                status, reason, score = _judge_survival(
                    impr, ctr, cvr, threshold, days_listed
                )

                # DB 저장
                record = ProductSurvivalStatus(
                    product_id=lst.product_id,
                    platform=plat,
                    analysis_date=today_str,
                    window_days=window_days,
                    days_since_listed=days_listed,
                    impressions=impr, clicks=clks, orders=ords, revenue=rev,
                    ctr=round(ctr, 5), cvr=round(cvr, 5),
                    survival_score=round(score, 1),
                    status=status,
                    reason=reason,
                )
                db.add(record)

                results.append({
                    "product_id": lst.product_id,
                    "platform": plat,
                    "window_days": window_days,
                    "impressions": impr,
                    "ctr": round(ctr * 100, 2),
                    "cvr": round(cvr * 100, 2),
                    "orders": ords,
                    "survival_score": round(score, 1),
                    "status": status,
                    "reason": reason,
                    "days_since_listed": days_listed,
                })

        db.commit()

    counts = {s: sum(1 for r in results if r["status"] == s)
              for s in [STATUS_HEALTHY, STATUS_WATCH, STATUS_DELETE]}
    logger.info("생존율 분석 완료 [%dd]: HEALTHY=%d WATCH=%d DELETE=%d",
                window_days, counts[STATUS_HEALTHY], counts[STATUS_WATCH], counts[STATUS_DELETE])
    return results


def _judge_survival(impressions: int, ctr: float, cvr: float,
                    threshold: SurvivalThreshold,
                    days_listed: int) -> tuple[str, str, float]:
    """생존 상태, 사유, 점수를 반환한다."""

    # 노출 점수 (0~100): threshold 대비 달성률
    impr_score = min(100.0, impressions / max(threshold.min_impressions, 1) * 100)

    # CTR 점수: threshold.min_ctr 대비
    ctr_score = min(100.0, ctr / max(threshold.min_ctr, 0.001) * 100)

    # CVR 점수: threshold.min_cvr 대비
    cvr_score = min(100.0, cvr / max(threshold.min_cvr, 0.001) * 100)

    score = impr_score * 0.30 + ctr_score * 0.35 + cvr_score * 0.35

    # 등록 초기(3일 미만)는 데이터 부족으로 WATCH 유지
    if days_listed < 3:
        return STATUS_WATCH, "등록 초기 — 데이터 축적 중", max(score, 40.0)

    # 노출 부족
    if impressions < threshold.min_impressions:
        if days_listed >= threshold.window_days:
            return STATUS_DELETE, f"노출 부족: {impressions}회 < {threshold.min_impressions}회 기준", score
        return STATUS_WATCH, f"노출 부족 관찰 중: {impressions}회", max(score, 30.0)

    # 노출 있음 — CTR 판정
    if ctr < threshold.min_ctr:
        return STATUS_DELETE, (f"CTR 미달: {ctr*100:.2f}% < {threshold.min_ctr*100:.1f}% "
                               f"(제목·썸네일 개선 필요)"), score

    # CTR 통과 — CVR 판정
    if cvr < threshold.min_cvr:
        return STATUS_WATCH, (f"CVR 미달: {cvr*100:.2f}% < {threshold.min_cvr*100:.1f}% "
                              f"(가격·상세페이지 개선 고려)"), score

    return STATUS_HEALTHY, "정상 판매 중", score


# ── 자동 삭제 후보 처리 ────────────────────────────────────────────────────────

def get_delete_candidates(platform: str = "all",
                          window_days: int = 14,
                          limit: int = 50) -> list[dict]:
    """DELETE_CANDIDATE 상태 상품 목록을 반환한다."""
    from app.db import get_db, ProductSurvivalStatus
    from sqlalchemy import desc

    platforms = ["coupang", "smartstore"] if platform == "all" else [platform]

    with get_db() as db:
        q = db.query(ProductSurvivalStatus).filter(
            ProductSurvivalStatus.status == STATUS_DELETE,
            ProductSurvivalStatus.window_days == window_days,
            ProductSurvivalStatus.auto_action == "",
        )
        if "all" not in platforms:
            q = q.filter(ProductSurvivalStatus.platform.in_(platforms))
        rows = q.order_by(desc(ProductSurvivalStatus.created_at)).limit(limit).all()

    return [{
        "id": r.id,
        "product_id": r.product_id,
        "platform": r.platform,
        "window_days": r.window_days,
        "impressions": r.impressions,
        "ctr": round(r.ctr * 100, 2),
        "cvr": round(r.cvr * 100, 2),
        "orders": r.orders,
        "survival_score": r.survival_score,
        "reason": r.reason,
        "days_since_listed": r.days_since_listed,
    } for r in rows]


def mark_as_delisted(product_id: int, platform: str) -> bool:
    """상품 삭제 완료 처리 (auto_action = 'delisted')."""
    from app.db import get_db, ProductSurvivalStatus
    from sqlalchemy import desc

    with get_db() as db:
        row = db.query(ProductSurvivalStatus).filter_by(
            product_id=product_id, platform=platform, status=STATUS_DELETE
        ).order_by(desc(ProductSurvivalStatus.created_at)).first()
        if row:
            row.status = STATUS_DELETED
            row.auto_action = "delisted"
            db.commit()
            return True
    return False


def get_survival_dashboard(platform: str = "all") -> dict:
    """생존율 현황 대시보드 집계."""
    from app.db import get_db, ProductSurvivalStatus
    from sqlalchemy import func

    with get_db() as db:
        # 최신 분석 날짜
        latest = db.query(
            func.max(ProductSurvivalStatus.analysis_date)
        ).scalar()
        if not latest:
            return {"error": "분석 데이터 없음"}

        rows = db.query(
            ProductSurvivalStatus.platform,
            ProductSurvivalStatus.window_days,
            ProductSurvivalStatus.status,
            func.count(ProductSurvivalStatus.id).label("cnt"),
        ).filter(
            ProductSurvivalStatus.analysis_date == latest
        ).group_by(
            ProductSurvivalStatus.platform,
            ProductSurvivalStatus.window_days,
            ProductSurvivalStatus.status,
        ).all()

    stats: dict = {"latest_date": latest, "by_platform": {}}
    for plat, window, status, cnt in rows:
        if plat not in stats["by_platform"]:
            stats["by_platform"][plat] = {}
        key = f"{window}d"
        if key not in stats["by_platform"][plat]:
            stats["by_platform"][plat][key] = {}
        stats["by_platform"][plat][key][status] = cnt

    return stats
