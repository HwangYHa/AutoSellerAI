from pathlib import Path


def test_market_seo_page_is_registered_in_sidebar():
    source = Path("gui/main.py").read_text(encoding="utf-8")
    assert 'pages/08_마켓_SEO_최적화_안전.py' in source
    assert 'label="마켓 SEO 최적화"' in source
    assert 'icon="📈"' in source


def test_market_seo_safe_entrypoint_installs_write_patch():
    source = Path("gui/pages/08_마켓_SEO_최적화_안전.py").read_text(encoding="utf-8")
    assert "install_market_seo_safe_writes()" in source
    patch_source = Path("app/seo/market_safe_runtime.py").read_text(encoding="utf-8")
    assert "retry_sqlite_write" in patch_source
    assert "MarketSeoOptimizer.approve_fields = _approve_fields" in patch_source
    assert "MarketSeoOptimizer.apply_audit = _apply_audit" in patch_source
    assert "MarketSeoOptimizer._persist = _persist" in patch_source
