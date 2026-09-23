from app.pricing.service import auto_price_bounds, calculate_target_price, margin_rate, round_price_up


def test_target_price_preserves_36_percent_margin_after_fee():
    price = calculate_target_price(18000, 0.11, 0.36, 900)
    assert price == 34900
    assert margin_rate(price, 18000, 0.11) >= 0.36


def test_rounding_policy_always_rounds_up():
    assert round_price_up(33962, 900) == 34900
    assert round_price_up(33101, 500) == 33500
    assert round_price_up(33101, 100) == 33200
    assert round_price_up(33101, 10) == 33110


def test_coupang_auto_floor_never_breaks_target_margin():
    base = calculate_target_price(18000, 0.108, 0.36, 900)
    floor, ceiling = auto_price_bounds(base, 18000, 0.108, 0.36, 15, 8, 900)
    assert floor >= calculate_target_price(18000, 0.108, 0.36, 900)
    assert ceiling >= base
