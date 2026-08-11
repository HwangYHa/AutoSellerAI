from __future__ import annotations

from app.db import Listing, Product, get_db, init_db
from app.sync.catalog_sync import _smartstore_search_page, _sync


def test_smartstore_search_uses_official_post_endpoint(monkeypatch):
    captured = {}

    class FakeUploader:
        def _headers(self):
            return {"Authorization": "Bearer test"}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"contents": [], "totalPages": 0, "last": True}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.sync.catalog_sync.httpx.post", fake_post)
    result = _smartstore_search_page(FakeUploader(), page=2, page_size=500)

    assert result["contents"] == []
    assert captured["url"].endswith("/external/v1/products/search")
    assert captured["json"]["page"] == 2
    assert captured["json"]["size"] == 500
    assert captured["json"]["orderType"] == "MOD_DATE"


def test_existing_marketplace_product_is_updated_not_skipped():
    init_db()
    platform = "smartstore"
    platform_id = "SYNC-TEST-20260811"
    sku = f"IMPORT-{platform}-{platform_id}"

    with get_db() as db:
        listings = db.query(Listing).filter_by(platform=platform, platform_id=platform_id).all()
        for row in listings:
            db.delete(row)
        product = db.query(Product).filter_by(sku=sku).first()
        if product:
            db.delete(product)
        db.commit()

    first = _sync(platform, [{
        "platform_id": platform_id,
        "name": "외부 등록 테스트 상품",
        "price": 19900,
        "category": "생활 > 테스트",
        "brand": "테스트브랜드",
        "image": "https://example.com/one.jpg",
        "status": "SALE",
    }])
    assert first["created"] == 1

    second = _sync(platform, [{
        "platform_id": platform_id,
        "name": "판매자센터에서 수정한 상품명",
        "price": 23900,
        "category": "생활 > 수정",
        "brand": "수정브랜드",
        "image": "https://example.com/two.jpg",
        "status": "SALE",
    }])
    assert second["updated"] == 1
    assert second["skipped"] == 0

    with get_db() as db:
        product = db.query(Product).filter_by(sku=sku).first()
        assert product is not None
        assert product.name == "판매자센터에서 수정한 상품명"
        assert product.sell_price == 23900
        assert product.category == "생활 > 수정"
        assert product.brand == "수정브랜드"

        listing = db.query(Listing).filter_by(platform=platform, platform_id=platform_id).first()
        assert listing is not None
        db.delete(listing)
        db.delete(product)
        db.commit()
