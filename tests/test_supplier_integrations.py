from types import SimpleNamespace

import app.suppliers.domeggook_openapi as dg
from app.suppliers.adapter_domeggook import DomeggookAdapter


def test_domeggook_search_uses_official_v41(monkeypatch):
    calls = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.update(params or {})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "domeggook": {
                    "header": {"numberOfItems": 1},
                    "list": {
                        "item": [{
                            "no": 123,
                            "title": "테스트 상품",
                            "price": 12000,
                            "priceOrg": 15000,
                            "unitQty": 1,
                            "thumb": "https://example.com/a.jpg",
                            "url": "https://example.com/product/123",
                            "deli": {"fee": 3000},
                        }]
                    },
                }
            },
        )

    monkeypatch.setattr(dg, "get_settings", lambda: SimpleNamespace(domeggook_api_key="KEY"))
    monkeypatch.setattr(dg.httpx, "get", fake_get)
    items = dg.search_products("청소기", limit=20, min_price=1000, max_moq=1)

    assert calls["ver"] == "4.1"
    assert calls["mode"] == "getItemList"
    assert calls["market"] == "dome"
    assert calls["kw"] == "청소기"
    assert calls["sz"] == 20
    assert len(items) == 1
    assert items[0].raw_id == "123"
    assert items[0].supply_price == 12000
    assert items[0].moq == 1


def test_domeggook_detail_uses_official_v46(monkeypatch):
    calls = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.update(params or {})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "domeggook": {
                    "basis": {"no": 123, "title": "상세 테스트"},
                    "price": {"dome": 10000, "domeOrg": 12000},
                    "qty": {"inventory": 50, "domeMoq": 1},
                    "deli": {"dome": {"fee": 2500}, "periodDeli": 1, "sendAvg": 0.8},
                    "image": "https://example.com/detail.jpg",
                }
            },
        )

    monkeypatch.setattr(dg, "get_settings", lambda: SimpleNamespace(domeggook_api_key="KEY"))
    monkeypatch.setattr(dg.httpx, "get", fake_get)
    item = dg.get_product("123")

    assert calls["ver"] == "4.6"
    assert calls["mode"] == "getItemView"
    assert item is not None
    assert item.name == "상세 테스트"
    assert item.stock == 50
    assert item.shipping_fee == 2500


def test_domeggook_adapter_available_with_api_key(monkeypatch):
    import app.suppliers.adapter_domeggook as adapter_module
    monkeypatch.setattr(adapter_module, "get_settings", lambda: SimpleNamespace(domeggook_api_key="KEY"))
    assert DomeggookAdapter().is_available() is True


def test_supplier_diagnostic_pages_exist_but_normal_navigation_is_unified():
    """Legacy diagnostic pages may exist during migration but must not fragment normal navigation."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert (root / "gui/pages/21_도매꾹_연동.py").exists()
    assert (root / "gui/pages/22_온채널_연동.py").exists()

    app_text = (root / "gui/app.py").read_text(encoding="utf-8")
    assert "Seller OS" in app_text
    assert "통합 상품 소싱" in app_text
    assert 'page_link("pages/21_도매꾹_연동.py"' not in app_text
    assert 'page_link("pages/22_온채널_연동.py"' not in app_text
