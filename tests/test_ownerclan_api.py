from __future__ import annotations

from types import SimpleNamespace

from app.suppliers.adapter_ownerclan import OwnerClanAdapter
from app.suppliers.ownerclan import OwnerClanClient


def test_ownerclan_token_extraction_supports_common_shapes():
    assert OwnerClanClient._extract_token("abc") == "abc"
    assert OwnerClanClient._extract_token({"token": "t1"}) == "t1"
    assert OwnerClanClient._extract_token({"access_token": "t2"}) == "t2"
    assert OwnerClanClient._extract_token({"data": {"jwt": "t3"}}) == "t3"
    assert OwnerClanClient._extract_token({}) == ""


def test_ownerclan_adapter_normalizes_options_price_and_stock():
    raw = {
        "key": "W000000",
        "name": "오너클랜 테스트 상품",
        "model": "MODEL-1",
        "options": [
            {
                "price": 35000,
                "quantity": 23,
                "optionAttributes": [
                    {"name": "색상", "value": "RED"},
                    {"name": "사이즈", "value": "95"},
                ],
            },
            {
                "price": 37000,
                "quantity": 7,
                "optionAttributes": [
                    {"name": "색상", "value": "BLUE"},
                    {"name": "사이즈", "value": "100"},
                ],
            },
        ],
    }

    product = OwnerClanAdapter()._normalize(raw)

    assert product.supplier_id == "ownerclan"
    assert product.raw_id == "W000000"
    assert product.name == "오너클랜 테스트 상품"
    assert product.supply_price == 35000
    assert product.stock == 30
    assert {x["name"] for x in product.options} == {"색상", "사이즈"}
    color = next(x for x in product.options if x["name"] == "색상")
    assert color["values"] == ["RED", "BLUE"]


def test_ownerclan_client_uses_sandbox_urls(monkeypatch):
    fake = SimpleNamespace(
        ownerclan_username="seller",
        ownerclan_password="pw",
        ownerclan_environment="sandbox",
    )
    monkeypatch.setattr("app.suppliers.ownerclan.get_settings", lambda: fake)
    client = OwnerClanClient()
    assert client.auth_url == "https://auth-sandbox.ownerclan.com/auth"
    assert client.graphql_url == "https://api-sandbox.ownerclan.com/v1/graphql"
    assert client.is_available() is True
