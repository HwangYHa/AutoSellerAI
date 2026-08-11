"""MOQ Engine — 재발주 포인트 계산, 최적 발주량 추천, 재고 상태 분류."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Inventory, Product


@dataclass
class ReorderSuggestion:
    product_id: int
    product_name: str
    sku: str
    supplier: str

    qty_on_hand: int
    qty_reserved: int
    qty_incoming: int
    available_qty: int          # on_hand - reserved

    safety_stock: int
    reorder_point: int
    moq: int
    reorder_qty: int
    lead_time_days: int
    unit_cost: float

    avg_daily_sales: float
    days_of_stock: float        # 현재 가용 재고로 버틸 수 있는 일수
    urgency: str                # critical | warning | ok
    suggested_qty: int          # MOQ 적용 최종 발주 수량
    suggested_cost: float       # 발주 예상 금액
    reason: str


@dataclass
class StockStatus:
    total_products: int = 0
    critical: int = 0       # 재고 = 0 또는 안전재고 미만
    warning: int = 0        # 재발주 포인트 이하
    ok: int = 0
    total_value: float = 0.0    # 현재 재고 원가 합계
    suggestions: list[ReorderSuggestion] = field(default_factory=list)


def _avg_daily_sales(product_id: int, orders, days: int = 30) -> float:
    """최근 N일 판매량 기반 일평균 판매량 계산."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    total_qty = sum(
        o.quantity for o in orders
        if o.product_id == product_id
        and o.status not in ("cancelled", "returned")
        and o.ordered_at >= cutoff
    )
    return total_qty / days


def classify_urgency(inv: "Inventory", avg_daily: float) -> tuple[str, float]:
    """urgency 분류 및 days_of_stock 계산."""
    available = inv.qty_on_hand - inv.qty_reserved
    if avg_daily > 0:
        days = available / avg_daily
    else:
        days = float("inf") if available > 0 else 0.0

    if available <= inv.safety_stock or available <= 0:
        return "critical", days
    if available <= inv.reorder_point:
        return "warning", days
    return "ok", days


def calculate_suggested_qty(inv: "Inventory", avg_daily: float) -> int:
    """MOQ 를 만족하는 최적 발주량.

    기본 공식: max(reorder_qty, ceil(avg_daily × (lead_time + 14)))
    최종 결과는 MOQ 의 배수로 올림.
    """
    if avg_daily > 0:
        demand_qty = math.ceil(avg_daily * (inv.lead_time_days + 14))
    else:
        demand_qty = inv.reorder_qty

    base = max(demand_qty, inv.reorder_qty, inv.moq)
    # MOQ 배수로 올림
    if inv.moq > 1:
        base = math.ceil(base / inv.moq) * inv.moq
    return base


def build_suggestions(
    inventories: list,
    products: list,
    orders: list,
) -> list[ReorderSuggestion]:
    """모든 재고 항목을 순회해 발주 필요 목록을 생성한다."""
    prod_map = {p.id: p for p in products}
    suggestions: list[ReorderSuggestion] = []

    for inv in inventories:
        prod = prod_map.get(inv.product_id)
        if not prod:
            continue

        avg_daily = _avg_daily_sales(inv.product_id, orders, days=30)
        urgency, days_of_stock = classify_urgency(inv, avg_daily)

        if urgency == "ok":
            continue

        suggested_qty = calculate_suggested_qty(inv, avg_daily)
        available = inv.qty_on_hand - inv.qty_reserved

        if urgency == "critical":
            reason = (
                f"재고 위험 — 가용 {available}개 (안전재고 {inv.safety_stock}개 미달)"
                if available > 0
                else "재고 소진"
            )
        else:
            days_str = f"{days_of_stock:.1f}일" if days_of_stock != float("inf") else "∞"
            reason = f"재발주 포인트 도달 — 가용 {available}개, 약 {days_str} 분량 남음"

        suggestions.append(
            ReorderSuggestion(
                product_id=inv.product_id,
                product_name=prod.name,
                sku=prod.sku,
                supplier=prod.source,
                qty_on_hand=inv.qty_on_hand,
                qty_reserved=inv.qty_reserved,
                qty_incoming=inv.qty_incoming,
                available_qty=available,
                safety_stock=inv.safety_stock,
                reorder_point=inv.reorder_point,
                moq=inv.moq,
                reorder_qty=inv.reorder_qty,
                lead_time_days=inv.lead_time_days,
                unit_cost=inv.unit_cost,
                avg_daily_sales=round(avg_daily, 2),
                days_of_stock=round(days_of_stock, 1) if days_of_stock != float("inf") else -1,
                urgency=urgency,
                suggested_qty=suggested_qty,
                suggested_cost=round(suggested_qty * inv.unit_cost, 0),
                reason=reason,
            )
        )

    # critical 먼저, 그다음 warning
    suggestions.sort(key=lambda s: (0 if s.urgency == "critical" else 1, s.days_of_stock))
    return suggestions


def auto_reorder_point(avg_daily: float, lead_time_days: int, safety_stock: int) -> int:
    """표준 공식: Safety Stock + (Avg Daily Sales × Lead Time)."""
    return safety_stock + math.ceil(avg_daily * lead_time_days)
