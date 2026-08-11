"""품절 위험 예측 엔진 (Stockout Risk Predictor).

[드랍쉬핑 최대 리스크]
  판매됨 → 공급사 품절 → 배송지연 클레임 → 계정 점수 하락

[예측 모델 - 4개 신호]
  1. 현재 재고 / 일평균 판매량 → 잔여 일수 계산
  2. 최근 30일 재고 변동 추이 (falling / stable / rising)
  3. 최근 30일 품절 발생 횟수
  4. 공급사 발주 성공률

[리스크 등급]
  CRITICAL : 잔여 3일 이하 또는 최근 품절 2회 이상
  HIGH     : 잔여 7일 이하 또는 품절 1회 이상
  MEDIUM   : 잔여 14일 이하
  LOW      : 잔여 14일 초과

[자동 조치]
  CRITICAL → 즉시 플랫폼 품절 처리 (재고 0 설정)
  HIGH     → 텔레그램 경고 + 재발주 추천
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

RISK_CRITICAL = "CRITICAL"
RISK_HIGH     = "HIGH"
RISK_MEDIUM   = "MEDIUM"
RISK_LOW      = "LOW"


@dataclass
class RiskResult:
    risk_level: str
    risk_score: float               # 0~100 (높을수록 위험)
    days_until_stockout: int
    stock_trend: str                # rising | stable | falling | critical
    recent_stockout_count: int
    fulfillment_rate: float
    reason: str


def predict_stockout_risk(
    product_id: int,
    supplier_id: str,
    current_stock: int,
    avg_daily_sales: float,
    recent_stockout_count: int = 0,
    fulfillment_rate: float = 1.0,
    stock_history: list[int] | None = None,  # [오래된→최신] 재고 스냅샷
) -> RiskResult:
    """단일 상품의 품절 위험도를 계산한다."""

    # 1. 잔여 일수 계산
    if avg_daily_sales > 0:
        days_left = int(current_stock / avg_daily_sales)
    else:
        days_left = 999  # 판매 없음 = 재고 소진 없음

    # 2. 재고 추이 계산
    trend = _calc_stock_trend(stock_history or [current_stock])

    # 3. 위험 점수 계산 (0~100)
    score = 0.0

    # 잔여 일수 기반 (50점)
    if days_left <= 1:      score += 50.0
    elif days_left <= 3:    score += 45.0
    elif days_left <= 7:    score += 35.0
    elif days_left <= 14:   score += 20.0
    elif days_left <= 30:   score += 10.0

    # 품절 이력 기반 (30점)
    score += min(30.0, recent_stockout_count * 15.0)

    # 발주 성공률 기반 (20점)
    score += (1.0 - min(1.0, fulfillment_rate)) * 20.0

    # 추이 보정
    if trend == "critical":  score = min(100.0, score + 15.0)
    elif trend == "falling": score = min(100.0, score + 8.0)
    elif trend == "rising":  score = max(0.0, score - 5.0)

    score = min(100.0, max(0.0, score))

    # 4. 등급 결정
    if days_left <= 3 or recent_stockout_count >= 2 or score >= 80:
        level = RISK_CRITICAL
        reason = f"잔여{days_left}일/최근품절{recent_stockout_count}회/발주성공률{fulfillment_rate:.0%}"
    elif days_left <= 7 or recent_stockout_count >= 1 or score >= 60:
        level = RISK_HIGH
        reason = f"잔여{days_left}일/품절이력있음/발주성공률{fulfillment_rate:.0%}"
    elif days_left <= 14 or score >= 40:
        level = RISK_MEDIUM
        reason = f"잔여{days_left}일/추이:{trend}"
    else:
        level = RISK_LOW
        reason = f"잔여{days_left}일/정상"

    return RiskResult(
        risk_level=level,
        risk_score=round(score, 1),
        days_until_stockout=days_left,
        stock_trend=trend,
        recent_stockout_count=recent_stockout_count,
        fulfillment_rate=fulfillment_rate,
        reason=reason,
    )


def _calc_stock_trend(history: list[int]) -> str:
    """재고 스냅샷 목록으로 추이를 계산한다."""
    if len(history) < 2:
        return "stable"

    recent = history[-7:] if len(history) >= 7 else history
    if recent[-1] == 0:
        return "critical"

    # 선형 추세
    n = len(recent)
    avg_change = (recent[-1] - recent[0]) / max(n - 1, 1)

    if avg_change > 5:
        return "rising"
    if avg_change < -10:
        return "falling"
    return "stable"


# ── 전체 상품 품절 위험 스캔 ───────────────────────────────────────────────────

def scan_all_products(auto_exclude_critical: bool = True) -> dict:
    """등록된 모든 상품의 품절 위험을 평가하고 DB에 저장한다.

    Returns: {"critical": int, "high": int, "medium": int, "low": int, "auto_excluded": int}
    """
    from app.db import get_db, Product, Inventory, StockoutRisk, Order, SupplierRawProduct
    from sqlalchemy import func

    stats = {"critical": 0, "high": 0, "medium": 0, "low": 0, "auto_excluded": 0}

    with get_db() as db:
        products = db.query(Product).filter(
            Product.status.in_(["ready", "listed"])
        ).all()

        for p in products:
            # 재고 현황
            inv = db.query(Inventory).filter_by(product_id=p.id).first()
            current_stock = inv.quantity if inv else 0

            # 일평균 판매량 (최근 30일)
            since = datetime.utcnow() - timedelta(days=30)
            sold = db.query(func.sum(Order.quantity)).filter(
                Order.product_id == p.id,
                Order.created_at >= since,
            ).scalar() or 0
            avg_daily = round(sold / 30.0, 2)

            # 공급사 정보
            raw = db.query(SupplierRawProduct).filter_by(
                product_id=p.id
            ).order_by(SupplierRawProduct.updated_at.desc()).first()
            supplier_id = raw.supplier_id if raw else p.source
            raw_id = raw.raw_id if raw else p.source_id

            # 발주 성공률: 최근 30일 발주 이력에서 계산
            from app.db import PurchaseOrderItem, PurchaseOrder
            po_items = db.query(PurchaseOrderItem).join(
                PurchaseOrder,
                PurchaseOrderItem.po_id == PurchaseOrder.id
            ).filter(
                PurchaseOrderItem.product_id == p.id,
                PurchaseOrder.created_at >= since,
            ).all()
            fulfill_rate = 1.0
            if po_items:
                fulfilled = sum(1 for i in po_items
                                if (i.received_qty or 0) >= (i.ordered_qty or 1))
                fulfill_rate = fulfilled / len(po_items)

            # 최근 품절 횟수 추정 (재고 0 스냅샷 수)
            stockout_count = 0
            if current_stock == 0 and avg_daily > 0:
                stockout_count = 1  # 현재 품절

            result = predict_stockout_risk(
                product_id=p.id,
                supplier_id=supplier_id,
                current_stock=current_stock,
                avg_daily_sales=avg_daily,
                recent_stockout_count=stockout_count,
                fulfillment_rate=fulfill_rate,
            )

            # DB 저장
            risk_row = StockoutRisk(
                product_id=p.id,
                supplier_id=supplier_id,
                raw_id=raw_id,
                risk_score=result.risk_score,
                risk_level=result.risk_level,
                current_stock=current_stock,
                avg_daily_sales=avg_daily,
                days_until_stockout=result.days_until_stockout,
                recent_stockout_count=result.recent_stockout_count,
                fulfillment_rate=result.fulfillment_rate,
                stock_trend=result.stock_trend,
                checked_at=datetime.utcnow(),
            )
            db.add(risk_row)

            level = result.risk_level.lower()
            if level in stats:
                stats[level] += 1

            # CRITICAL 자동 제외
            if auto_exclude_critical and result.risk_level == RISK_CRITICAL:
                risk_row.is_excluded = True
                risk_row.excluded_at = datetime.utcnow()
                p.status = "paused"  # 플랫폼에서 노출 중단
                stats["auto_excluded"] += 1
                logger.warning("품절위험 자동제외: product_id=%d (%s)", p.id, result.reason)

        db.commit()

    logger.info("품절 위험 스캔 완료: %s", stats)
    return stats


def get_risk_summary() -> dict:
    """현재 품절 위험 등급별 집계."""
    from app.db import get_db, StockoutRisk
    from sqlalchemy import func

    with get_db() as db:
        rows = db.query(
            StockoutRisk.risk_level,
            func.count(StockoutRisk.id).label("cnt"),
        ).filter(
            StockoutRisk.is_excluded == False,
            StockoutRisk.checked_at >= datetime.utcnow() - timedelta(hours=25),
        ).group_by(StockoutRisk.risk_level).all()

    return {row.risk_level: row.cnt for row in rows}


def get_high_risk_products(limit: int = 20) -> list[dict]:
    """HIGH 이상 위험 상품 목록 (대시보드·알림용)."""
    from app.db import get_db, StockoutRisk, Product

    with get_db() as db:
        rows = db.query(StockoutRisk, Product).join(
            Product, StockoutRisk.product_id == Product.id
        ).filter(
            StockoutRisk.risk_level.in_([RISK_CRITICAL, RISK_HIGH]),
            StockoutRisk.is_excluded == False,
        ).order_by(
            StockoutRisk.risk_score.desc()
        ).limit(limit).all()

    return [{
        "product_id": r.product_id,
        "product_name": p.name[:50],
        "supplier_id": r.supplier_id,
        "risk_level": r.risk_level,
        "risk_score": r.risk_score,
        "current_stock": r.current_stock,
        "days_until_stockout": r.days_until_stockout,
        "avg_daily_sales": r.avg_daily_sales,
        "stock_trend": r.stock_trend,
        "fulfillment_rate": round(r.fulfillment_rate * 100, 1),
    } for r, p in rows]
