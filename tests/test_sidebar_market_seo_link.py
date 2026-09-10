from pathlib import Path


def test_market_seo_page_is_registered_in_sidebar():
    source = Path("gui/main.py").read_text(encoding="utf-8")
    assert 'pages/08_마켓_SEO_최적화.py' in source
    assert 'label="마켓 SEO 최적화"' in source
    assert 'icon="📈"' in source
