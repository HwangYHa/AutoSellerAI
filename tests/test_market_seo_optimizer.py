from __future__ import annotations

from pathlib import Path

import httpx

from app.db import Listing, Product, get_db, init_db
from app.seo.market_api import CoupangSeoApi, NaverSeoApi, _clean_coupang_tags, _clean_naver_tags
from app.seo.market_optimizer import MarketSeoOptimizer, classify_performance, normalize_title


def test_title_normalizer_removes_promotional_noise_without_inventing_specs():
    title = normalize_title("초특가 프리미엄 차량용 무선 청소기 청소기", "키스토이")
    assert "초특가" not in title
    assert "프리미엄" not in title
    assert title.startswith("키스토이")
    assert title.split().count("청소기") == 1
    assert "120W" not in title


def test_performance_classification_uses_real_signals_only():
    assert classify_performance({"has_traffic_metrics": True, "impressions": 10, "clicks": 0, "orders": 0, "ctr": 0, "cvr": 0}, 50) == "NO_EXPOSURE_SIGNAL"
    assert classify_performance({"has_traffic_metrics": True, "impressions": 1000, "clicks": 2, "orders": 0, "ctr": .002, "cvr": 0}, 50) == "LOW_CTR_SIGNAL"
    assert classify_performance({"has_traffic_metrics": True, "impressions": 1000, "clicks": 30, "orders": 0, "ctr": .03, "cvr": 0}, 50) == "LOW_CONVERSION_SIGNAL"
    assert classify_performance({"has_traffic_metrics": False, "orders": 0}, 90) == "HEALTHY"


def test_market_tag_cleaners_enforce_platform_limits():
    cp = _clean_coupang_tags(["차량용청소기"] * 2 + [f"키워드{i}" for i in range(30)])
    assert len(cp) == 20
    assert len(set(cp)) == len(cp)
    assert all(len(x) <= 20 for x in cp)

    nv = _clean_naver_tags([{"code": 7, "text": "차량용 청소기"}, "차량용 청소기", "핸디@청소기"])
    assert len(nv) == 2
    assert nv[0] == {"code": 7, "text": "차량용 청소기"}
    assert nv[1]["text"] == "핸디청소기"


class _FakeCoupangUploader:
    def __init__(self):
        self.sent = None
        self.detail = {
            "sellerProductId": 991,
            "statusName": "승인완료",
            "displayCategoryCode": 123,
            "sellerProductName": "기존 발주 상품명",
            "displayProductName": "초특가 차량용 청소기",
            "generalProductName": "차량용 청소기",
            "brand": "",
            "deliveryChargeType": "FREE",
            "deliveryCharge": 0,
            "items": [{
                "sellerProductItemId": 11, "vendorItemId": 22,
                "salePrice": 19900,
                "attributes": [], "searchTags": [],
                "images": [{"imageType": "REPRESENTATION", "vendorPath": "https://example.test/a.jpg"}],
                "contents": [{"contentsType": "TEXT", "contentDetails": [{"content": "old", "detailType": "TEXT"}]}],
            }],
        }

    def get_seller_product(self, _seller_product_id):
        import copy
        return copy.deepcopy(self.detail)

    def _put(self, path, payload):
        self.sent = (path, payload)
        return httpx.Response(200, json={"code": "SUCCESS"}, request=httpx.Request("PUT", "https://example.test" + path))


def test_coupang_live_apply_changes_only_explicit_safe_fields():
    uploader = _FakeCoupangUploader()
    api = CoupangSeoApi(uploader=uploader)
    result = api.apply_fields(
        "991",
        {"title": "차량용 무선 청소기", "tags": ["차량용청소기", "무선청소기"], "category": "999", "price": 1, "shipping": {"charge": 9999}},
        {"title", "tags", "category", "price", "shipping"},
    )
    assert result["ok"] is True
    _, body = uploader.sent
    assert body["displayProductName"] == "차량용 무선 청소기"
    assert body["searchTags"] == ["차량용청소기", "무선청소기"]
    assert body["displayCategoryCode"] == 123
    assert body["deliveryCharge"] == 0
    assert body["items"][0]["salePrice"] == 19900


class _FakeNaverUploader:
    def _headers(self):
        return {"Authorization": "Bearer test", "Content-Type": "application/json"}


def test_naver_live_apply_uses_v2_origin_product_and_preserves_locked_fields(monkeypatch):
    api = NaverSeoApi(uploader=_FakeNaverUploader())
    payload = {
        "originProduct": {
            "name": "기존 상품명", "leafCategoryId": "5001", "salePrice": 25000,
            "detailContent": "old", "stockQuantity": 3,
            "images": {"representativeImage": {"url": "https://example.test/a.jpg"}},
            "deliveryInfo": {"deliveryFee": {"deliveryFeeType": "FREE"}},
            "detailAttribute": {"seoInfo": {"sellerTags": []}, "naverShoppingSearchInfo": {}},
        }
    }
    sent = {}
    monkeypatch.setattr(api, "get_product", lambda _id: payload)

    def fake_put(path, body, timeout=40):
        sent["path"] = path; sent["body"] = body
        return httpx.Response(200, json={"originProductNo": 88}, request=httpx.Request("PUT", "https://example.test" + path))

    monkeypatch.setattr(api, "_put", fake_put)
    result = api.apply_fields("88", {"title": "새 상품명", "tags": [{"text": "검색 태그"}], "category": "9999", "price": 1}, {"title", "tags", "category", "price"})
    assert result["ok"] is True
    assert sent["path"] == "/v2/products/origin-products/88"
    origin = sent["body"]["originProduct"]
    assert origin["name"] == "새 상품명"
    assert origin["leafCategoryId"] == "5001"
    assert origin["salePrice"] == 25000
    assert origin["detailAttribute"]["seoInfo"]["sellerTags"] == [{"text": "검색 태그"}]


class _FakeCoupangSeo:
    def get_product(self, _id):
        return _FakeCoupangUploader().detail

    current_fields = staticmethod(CoupangSeoApi.current_fields)

    def category_valid(self, _code):
        return True, "ok"

    def get_category_metadata(self, _code):
        return {"attributes": [{"attributeTypeName": "색상", "required": "MANDATORY", "groupNumber": "NONE", "exposed": "EXPOSED"}]}, "ok"

    def recommend_category(self, _product):
        return {"displayCategoryCode": "123", "name": "청소기"}, "ok"

    def get_histories(self, _id, max_pages=2):
        return [], "ok"

    def apply_fields(self, *_args, **_kwargs):
        return {"ok": True, "before": {}, "after": {}}


class _FakeNaverSeo:
    def apply_fields(self, *_args, **_kwargs):
        return {"ok": True, "before": {}, "after": {}}


def test_end_to_end_selected_audit_persists_required_attribute_problem():
    init_db()
    with get_db() as db:
        p = Product(
            sku="SEO-INTEGRATION-001", source="test", source_id="src-1", name="초특가 차량용 청소기",
            supply_price=10000, sell_price=19900, category="청소기", brand="테스트브랜드",
            origin="대한민국", material="ABS", images="[]", detail_images="[]", options="[]",
            detail_html="<h3>차량 실내 청소용</h3>", status="listed",
        )
        db.add(p); db.flush()
        listing = Listing(product_id=p.id, platform="coupang", platform_id="991", status="success")
        db.add(listing); db.commit(); product_id = p.id

    opt = MarketSeoOptimizer(coupang_api=_FakeCoupangSeo(), naver_api=_FakeNaverSeo())
    rows = opt.audit_selected(platforms=["coupang"], product_ids=[product_id], deep=True)
    assert len(rows) == 1
    audit = rows[0]
    assert audit["id"] is not None
    assert any(x["code"] == "COUPANG_REQUIRED_ATTR_MISSING" for x in audit["issues"])
    assert any(x["code"] == "COUPANG_TAGS_EMPTY" for x in audit["issues"])
    assert audit["proposed"]["category"] == "123"
    assert "공개 API" in " ".join(audit["limitations"])


def test_ui_exposes_individual_selected_and_bulk_workflows_and_locked_fields():
    page = Path(__file__).resolve().parents[1] / "gui/pages/08_마켓_SEO_최적화.py"
    text = page.read_text(encoding="utf-8")
    assert "전체 상품 자동 진단" in text
    assert "선택 상품만 진단" in text
    assert "이 상품 선택 필드 적용" in text
    assert "승인 필드 일괄 적용" in text
    assert "카테고리·가격·배송·이미지·미확인 속성값" in text
    assert "검색 상위노출을 보장" in text
