from app.seo.market_optimizer import MarketSeoOptimizer


def test_market_seo_safe_writes_are_installed_globally():
    assert getattr(MarketSeoOptimizer, "_sqlite_safe_writes_installed", False) is True
    assert MarketSeoOptimizer.approve_fields.__module__ == "app.seo.market_safe_runtime"
    assert MarketSeoOptimizer.apply_audit.__module__ == "app.seo.market_safe_runtime"
    assert MarketSeoOptimizer.apply_many.__module__ == "app.seo.market_safe_runtime"
    assert MarketSeoOptimizer._persist.__module__ == "app.seo.market_safe_runtime"
