"""세금 계산 엔진 — 부가세(VAT) + 종합소득세(2024 기준)."""
from __future__ import annotations
from dataclasses import dataclass


# ── 종합소득세 세율 구간 (2024 기준) ────────────────────────────────────────
# (하한, 상한, 세율, 누진공제액)  단위: 원
INCOME_TAX_BRACKETS: list[tuple[float, float, float, float]] = [
    (0,           14_000_000,   0.06, 0),
    (14_000_000,  50_000_000,   0.15, 1_260_000),
    (50_000_000,  88_000_000,   0.24, 5_760_000),
    (88_000_000,  150_000_000,  0.35, 15_440_000),
    (150_000_000, 300_000_000,  0.38, 19_940_000),
    (300_000_000, 500_000_000,  0.40, 25_940_000),
    (500_000_000, 1_000_000_000, 0.42, 35_940_000),
    (1_000_000_000, float("inf"), 0.45, 65_940_000),
]

# 지방소득세: 소득세의 10%
LOCAL_TAX_RATE = 0.10

# 소상공인 단순경비율 (업종별 상이, 전자상거래 기본 추정)
SIMPLIFIED_EXPENSE_RATIO = 0.70

# 부가세율
VAT_RATE = 0.10


@dataclass
class TaxEstimate:
    """세금 추정 결과."""
    year: int
    quarter: int           # 1~4 (전체 연간이면 0)

    gross_revenue: float   # 총매출 (VAT 포함)
    revenue_excl_vat: float  # 공급가액 (VAT 제외)

    # 부가세
    vat_output: float      # 매출세액
    vat_input: float       # 매입세액
    vat_payable: float     # 납부 부가세

    # 종합소득세
    taxable_income: float  # 과세 소득
    income_tax: float      # 종합소득세
    local_tax: float       # 지방소득세
    total_tax: float       # 합산 세금

    effective_rate: float  # 실효세율 (총세금 / 매출)


def calculate_tax(
    gross_revenue: float,
    supply_cost: float = 0.0,
    platform_fee: float = 0.0,
    shipping_cost: float = 0.0,
    ad_cost: float = 0.0,
    other_deductibles: float = 0.0,
    year: int = 2026,
    quarter: int = 0,
    use_simplified_rate: bool = False,
) -> TaxEstimate:
    """세금을 추정한다.

    use_simplified_rate=True이면 종합소득세 단순경비율(70%) 적용.
    False이면 실제 비용(공급가+수수료+배송비+광고비+기타)으로 계산.
    """
    # 부가세
    revenue_excl_vat = gross_revenue / (1 + VAT_RATE)
    vat_output = revenue_excl_vat * VAT_RATE
    vat_input = supply_cost / (1 + VAT_RATE) * VAT_RATE
    vat_payable = max(0.0, vat_output - vat_input)

    # 종합소득세 과세소득
    if use_simplified_rate:
        total_expense = gross_revenue * SIMPLIFIED_EXPENSE_RATIO
    else:
        total_expense = supply_cost + platform_fee + shipping_cost + ad_cost + other_deductibles

    taxable_income = max(0.0, gross_revenue - total_expense)
    income_tax = _calc_income_tax(taxable_income)
    local_tax = income_tax * LOCAL_TAX_RATE
    total_tax = vat_payable + income_tax + local_tax
    effective_rate = total_tax / gross_revenue if gross_revenue > 0 else 0.0

    return TaxEstimate(
        year=year,
        quarter=quarter,
        gross_revenue=gross_revenue,
        revenue_excl_vat=revenue_excl_vat,
        vat_output=vat_output,
        vat_input=vat_input,
        vat_payable=vat_payable,
        taxable_income=taxable_income,
        income_tax=income_tax,
        local_tax=local_tax,
        total_tax=total_tax,
        effective_rate=effective_rate,
    )


def _calc_income_tax(taxable_income: float) -> float:
    """누진세율로 종합소득세를 계산한다."""
    for low, high, rate, deduction in INCOME_TAX_BRACKETS:
        if taxable_income <= high:
            return max(0.0, taxable_income * rate - deduction)
    return 0.0


def quarterly_breakdown(annual_revenue: float, monthly_revenues: list[float]) -> list[dict]:
    """월별 매출 리스트에서 분기별 세금 추정을 반환한다."""
    quarters = []
    for q in range(4):
        months = monthly_revenues[q * 3: q * 3 + 3]
        qrev = sum(months)
        if qrev <= 0:
            continue
        est = calculate_tax(qrev, year=2026, quarter=q + 1)
        quarters.append({
            "quarter": q + 1,
            "label": f"Q{q+1}",
            "months": months,
            "gross_revenue": qrev,
            "vat_payable": est.vat_payable,
            "income_tax": est.income_tax + est.local_tax,
            "total_tax": est.total_tax,
        })
    return quarters


def format_krw(amount: float) -> str:
    """금액을 한국 원화 표기로 포맷한다."""
    if abs(amount) >= 100_000_000:
        return f"{amount / 100_000_000:.1f}억원"
    if abs(amount) >= 10_000:
        return f"{amount / 10_000:.1f}만원"
    return f"{amount:,.0f}원"
