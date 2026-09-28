from app.pricing.models import PricingPolicy


def test_pricing_policy_defaults_match_operating_policy():
    table = PricingPolicy.__table__
    assert table.c.coupang_fallback_fee_rate.default.arg == 0.105
    assert table.c.coupang_auto_up_pct.default.arg == 5.0
