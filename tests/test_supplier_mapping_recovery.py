from __future__ import annotations

from app.db import Listing, Product, SupplierRawProduct, get_db, init_db
from app.pipeline import _save_raw_products
from app.pricing.service import margin_rate
from app.pricing.supply_monitor import _raw_id_from_supplier_url, _supplier_from_url
from app.suppliers.base import NormalizedProduct
from app.sync.catalog_sync import _find_or_link_product


def test_unknown_supply_price_never_reports_fake_margin():
    assert margin_rate(10_000, 0, 0.105) == 0.0


def test_supplier_url_lineage_detection():
    url = "https://ownerclan.com/V2/product/view.php?itemCode=OC-1234"
    assert _supplier_from_url(url) == "ownerclan"
    assert _raw_id_from_supplier_url("ownerclan", url) == "OC-1234"


def test_reverse_sync_links_existing_supplier_product_by_embedded_sku():
    init_db()
    sku = "LIN-RECOVERY-TEST-001"
    platform_id = "LINEAGE-MARKET-001"

    with get_db() as db:
        old_listing = db.query(Listing).filter_by(platform="smartstore", platform_id=platform_id).first()
        if old_listing:
            db.delete(old_listing)
        old = db.query(Product).filter_by(sku=sku).first()
        if old:
            db.delete(old)
        db.commit()

        product = Product(
            sku=sku,
            source="ownerclan",
            source_id="OC-LINEAGE-001",
            source_url="https://ownerclan.com/V2/product/view.php?itemCode=OC-LINEAGE-001",
            name="공급사 원본 계보 테스트",
            supply_price=12_300,
            sell_price=19_900,
            status="listed",
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        product_id = product.id

        linked, created = _find_or_link_product(
            db,
            "smartstore",
            platform_id,
            {
                "name": "마켓에서 바뀐 상품명이라 이름으로는 찾기 어려움",
                "price": 19_900,
                "seller_sku": sku,
            },
        )
        assert created is False
        assert linked.id == product_id

        db.delete(product)
        db.commit()


def test_supplier_raw_cache_is_upserted_not_frozen():
    init_db()
    supplier_id = "ownerclan"
    raw_id = "RAW-CACHE-UPSERT-001"

    with get_db() as db:
        old = db.query(SupplierRawProduct).filter_by(
            supplier_id=supplier_id, raw_id=raw_id
        ).first()
        if old:
            db.delete(old)
            db.commit()

    first = NormalizedProduct(
        supplier_id=supplier_id,
        raw_id=raw_id,
        raw_url="https://example.com/1",
        name="캐시 갱신 테스트",
        supply_price=10_000,
        stock=3,
    )
    second = NormalizedProduct(
        supplier_id=supplier_id,
        raw_id=raw_id,
        raw_url="https://example.com/2",
        name="캐시 갱신 테스트",
        supply_price=11_500,
        stock=7,
    )
    _save_raw_products([first])
    _save_raw_products([second])

    with get_db() as db:
        row = db.query(SupplierRawProduct).filter_by(
            supplier_id=supplier_id, raw_id=raw_id
        ).first()
        assert row is not None
        assert row.raw_price == 11_500
        assert row.raw_stock == 7
        assert row.raw_url == "https://example.com/2"
        db.delete(row)
        db.commit()
