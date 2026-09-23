from app.pricing.change_control import classify_change_guard


def test_large_increase_requires_extra_confirmation():
    level, reason, pct = classify_change_guard(
        current_price=10000,
        target_price=12000,
        eligible=True,
        sales_count=0,
    )
    assert level == "SENSITIVE"
    assert pct == 20.0
    assert "인상" in reason


def test_large_decrease_requires_extra_confirmation():
    level, reason, pct = classify_change_guard(
        current_price=10000,
        target_price=9000,
        eligible=True,
        sales_count=0,
    )
    assert level == "SENSITIVE"
    assert pct == -10.0
    assert "인하" in reason


def test_sales_history_five_percent_change_requires_confirmation():
    level, reason, pct = classify_change_guard(
        current_price=20000,
        target_price=21000,
        eligible=True,
        sales_count=3,
    )
    assert level == "SENSITIVE"
    assert pct == 5.0
    assert "판매이력 3건" in reason


def test_small_change_without_sales_is_normal():
    level, reason, pct = classify_change_guard(
        current_price=20000,
        target_price=21000,
        eligible=True,
        sales_count=0,
    )
    assert level == "NORMAL"
    assert pct == 5.0
    assert reason == "일반 변경"


def test_ineligible_change_is_blocked():
    level, reason, pct = classify_change_guard(
        current_price=20000,
        target_price=25000,
        eligible=False,
        sales_count=0,
    )
    assert level == "BLOCKED"
    assert pct == 0.0
    assert "안전조건" in reason


def test_same_price_is_unchanged():
    level, reason, pct = classify_change_guard(
        current_price=34900,
        target_price=34900,
        eligible=True,
        sales_count=10,
    )
    assert level == "UNCHANGED"
    assert pct == 0.0
    assert "변경 없음" in reason
