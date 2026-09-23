from app.pricing.supply_monitor import classify_price_risk


def test_stale_supplier_price_blocks_remote_price_change():
    level, reason = classify_price_risk(
        eligible=False,
        supply_price=18000,
        current_price=34900,
        margin_rate=0.374,
        target_margin_rate=0.36,
        supply_fresh=False,
        supply_safe=True,
    )
    assert level == "BLOCKED"
    assert "최신화" in reason


def test_unverified_supplier_mapping_blocks_remote_price_change():
    level, reason = classify_price_risk(
        eligible=False,
        supply_price=18000,
        current_price=34900,
        margin_rate=0.374,
        target_margin_rate=0.36,
        supply_fresh=True,
        supply_safe=False,
    )
    assert level == "BLOCKED"
    assert "매핑" in reason


def test_negative_margin_is_critical():
    level, reason = classify_price_risk(
        eligible=True,
        supply_price=30000,
        current_price=25000,
        margin_rate=-0.31,
        target_margin_rate=0.36,
        supply_fresh=True,
        supply_safe=True,
    )
    assert level == "CRITICAL"
    assert "적자" in reason


def test_margin_below_target_is_warning():
    level, _ = classify_price_risk(
        eligible=True,
        supply_price=18000,
        current_price=32000,
        margin_rate=0.33,
        target_margin_rate=0.36,
        supply_fresh=True,
        supply_safe=True,
    )
    assert level == "WARNING"


def test_high_margin_is_review_not_automatic_problem():
    level, reason = classify_price_risk(
        eligible=True,
        supply_price=10000,
        current_price=50000,
        margin_rate=0.69,
        target_margin_rate=0.36,
        supply_fresh=True,
        supply_safe=True,
    )
    assert level == "REVIEW"
    assert "가격 경쟁력" in reason
