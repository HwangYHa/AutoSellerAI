"""정산 계산 엔진 — 플랫폼별 수수료, 순이익, 정산 주기."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime


# ── 플랫폼 수수료율 ───────────────────────────────────────────────────────────
# 쿠팡: Wing 판매 수수료 (카테고리 기본 10.8%)
# 스마트스토어: 카테고리별 2.0%~6.0%, 기본 3.5%
PLATFORM_FEE_RATES: dict[str, dict[str, float]] = {
    "coupang": {
        "default": 0.108,
        "food": 0.108,
        "fashion": 0.108,
        "digital": 0.108,
        "beauty": 0.108,
        "sports": 0.108,
    },
    "smartstore": {
        "default": 0.035,
        "fashion_clothes": 0.030,
        "fashion_accessories": 0.030,
        "digital_appliances": 0.027,
        "food": 0.020,
        "sports": 0.035,
        "beauty": 0.035,
        "living": 0.040,
    },
}

# 정산 주기 안내
SETTLEMENT_CYCLES: dict[str, str] = {
    "coupang": "주 2회 (화·금 정산)",
    "smartstore": "월 2회 (매월 1일·16일 정산)",
}

# 기본 배송비 (판매자 부담)
DEFAULT_SHIPPING_FEE = 3_000


@dataclass
class OrderProfit:
    """주문 1건 순이익 분석 결과."""
    platform: str
    quantity: int
    unit_sale_price: float
    unit_supply_price: float

    gross_revenue: float          # 총 매출 (판매가 × 수량)
    supply_cost: float            # 공급 원가
    platform_fee: float           # 플랫폼 수수료
    net_shipping_cost: float      # 순 배송비 (지불 - 청구)
    ad_cost: float                # 광고비
    return_cost: float            # 반품 처리비

    gross_profit: float           # 영업이익 (세전)
    vat_output: float             # 매출세액 (부가세)
    vat_input: float              # 매입세액 (공급사 세금계산서)
    vat_payable: float            # 납부 부가세
    net_profit: float             # 순이익 (VAT 차감 후)
    margin_rate: float            # 순이익률

    platform_fee_rate: float      # 적용된 수수료율


def calculate_order_profit(
    platform: str,
    unit_sale_price: float,
    unit_supply_price: float,
    quantity: int = 1,
    shipping_fee_paid: float = DEFAULT_SHIPPING_FEE,
    shipping_fee_charged: float = 0.0,
    platform_fee_rate: float | None = None,
    category_key: str = "default",
    ad_cost: float = 0.0,
    return_cost: float = 0.0,
) -> OrderProfit:
    """주문 순이익을 계산한다.

    shipping_fee_paid: 판매자가 택배사에 실제 지불한 배송비
    shipping_fee_charged: 구매자에게 청구한 배송비 (무료배송이면 0)
    """
    if platform_fee_rate is None:
        rates = PLATFORM_FEE_RATES.get(platform, {})
        platform_fee_rate = rates.get(category_key, rates.get("default", 0.108))

    gross_revenue = unit_sale_price * quantity
    supply_cost = unit_supply_price * quantity
    platform_fee = gross_revenue * platform_fee_rate
    net_shipping_cost = max(0.0, shipping_fee_paid - shipping_fee_charged)

    gross_profit = gross_revenue - supply_cost - platform_fee - net_shipping_cost - ad_cost - return_cost

    # 부가세: 판매가는 VAT 포함가이므로 공급가액 = 판매가 / 1.1
    vat_output = gross_revenue / 11.0        # 매출세액 = 매출 × 10/110
    vat_input = supply_cost / 11.0           # 매입세액 (세금계산서 수령 가정)
    vat_payable = max(0.0, vat_output - vat_input)

    net_profit = gross_profit - vat_payable
    margin_rate = net_profit / gross_revenue if gross_revenue > 0 else 0.0

    return OrderProfit(
        platform=platform,
        quantity=quantity,
        unit_sale_price=unit_sale_price,
        unit_supply_price=unit_supply_price,
        gross_revenue=gross_revenue,
        supply_cost=supply_cost,
        platform_fee=platform_fee,
        net_shipping_cost=net_shipping_cost,
        ad_cost=ad_cost,
        return_cost=return_cost,
        gross_profit=gross_profit,
        vat_output=vat_output,
        vat_input=vat_input,
        vat_payable=vat_payable,
        net_profit=net_profit,
        margin_rate=margin_rate,
        platform_fee_rate=platform_fee_rate,
    )


@dataclass
class PeriodSummary:
    """기간별 정산 요약."""
    order_count: int = 0
    gross_revenue: float = 0.0
    supply_cost: float = 0.0
    platform_fee: float = 0.0
    shipping_cost: float = 0.0
    ad_cost: float = 0.0
    return_cost: float = 0.0
    vat_payable: float = 0.0
    net_profit: float = 0.0

    @property
    def margin_rate(self) -> float:
        return self.net_profit / self.gross_revenue if self.gross_revenue > 0 else 0.0


def aggregate_orders(orders: list[dict]) -> PeriodSummary:
    """주문 목록을 합산해 기간 요약을 반환한다."""
    s = PeriodSummary()
    for o in orders:
        s.order_count += o.get("quantity", 1)
        s.gross_revenue += o.get("gross_revenue", 0)
        s.supply_cost += o.get("supply_cost", 0)
        s.platform_fee += o.get("platform_fee", 0)
        s.shipping_cost += o.get("net_shipping_cost", 0)
        s.ad_cost += o.get("ad_cost", 0)
        s.return_cost += o.get("return_cost", 0)
        s.vat_payable += o.get("vat_payable", 0)
        s.net_profit += o.get("net_profit", 0)
    return s


def next_settlement_date(platform: str, from_date: date | None = None) -> str:
    """다음 정산 예정일을 문자열로 반환."""
    today = from_date or date.today()
    if platform == "coupang":
        # 화(1)·금(4) 기준
        wd = today.weekday()
        days_to_tue = (1 - wd) % 7 or 7
        days_to_fri = (4 - wd) % 7 or 7
        days = min(days_to_tue, days_to_fri)
        target = today.replace(day=today.day + days).__class__.fromordinal(
            today.toordinal() + days
        )
        return target.strftime("%Y-%m-%d (화·금)")
    elif platform == "smartstore":
        d = today.day
        if d < 16:
            target = today.replace(day=16)
        else:
            import calendar
            last_day = calendar.monthrange(today.year, today.month)[1]
            if today.month == 12:
                target = today.replace(year=today.year + 1, month=1, day=1)
            else:
                target = today.replace(month=today.month + 1, day=1)
        return target.strftime("%Y-%m-%d (1일·16일)")
    return "미확인"
