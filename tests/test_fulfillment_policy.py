from types import SimpleNamespace

from app.policies.fulfillment import resolve_policy_for_product


def test_unknown_origin_is_not_forced_to_china(monkeypatch):
    import app.policies.fulfillment as mod
    settings = SimpleNamespace(
        seller_default_origin="",
        naver_origin_area_content="",
        seller_default_shipping_fee=3000,
        seller_default_return_fee=3000,
        coupang_return_charge=0,
        coupang_company_contact_number="",
        naver_after_service_phone="",
        seller_support_phone="010-1111-2222",
        coupang_delivery_company_code="",
        naver_delivery_company_code="",
        seller_default_delivery_company_code="",
    )
    monkeypatch.setattr(mod, "get_settings", lambda: settings)
    p = SimpleNamespace(source="smartstore_import", source_id="1", origin="")
    policy = resolve_policy_for_product(p, "smartstore")
    assert policy.origin == "기타해외"
    assert policy.provenance["origin"] == "seller_fallback"


def test_seller_account_fields_are_separate_from_product_facts(monkeypatch):
    import app.policies.fulfillment as mod
    settings = SimpleNamespace(
        seller_default_origin="한국",
        naver_origin_area_content="",
        seller_default_shipping_fee=2500,
        seller_default_return_fee=4000,
        coupang_return_charge=5000,
        coupang_company_contact_number="010-9999-0000",
        naver_after_service_phone="",
        seller_support_phone="010-1111-2222",
        coupang_delivery_company_code="CJGLS",
        naver_delivery_company_code="",
        seller_default_delivery_company_code="",
    )
    monkeypatch.setattr(mod, "get_settings", lambda: settings)
    p = SimpleNamespace(source="coupang_import", source_id="2", origin="한국")
    policy = resolve_policy_for_product(p, "coupang")
    assert policy.origin == "한국"
    assert policy.support_phone == "010-9999-0000"
    assert policy.return_fee == 5000
    assert policy.shipping_fee == 2500
