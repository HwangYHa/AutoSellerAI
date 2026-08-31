from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect

from app.db import _get_engine, get_db
from app.os.approvals import make_idempotency_key, payload_hash
from app.os.bridge import migrate_legacy_to_os
from app.os.catalog_contracts import SupplierCatalogItem, SupplierCatalogVariant
from app.os.models import OSListing, OSProduct
from app.os.quality_models import OSOfferVerification
from app.os.schema import ensure_os_schema, get_os_health
from app.os.state import FULFILLMENT_STATES, LISTING_STATES, PRODUCT_STATES


def test_os_schema_contains_canonical_spine_and_safety_tables():
    ensure_os_schema()
    names = set(inspect(_get_engine()).get_table_names())
    expected = {
        "os_suppliers",
        "os_products",
        "os_product_variants",
        "os_supplier_offers",
        "os_offer_verifications",
        "os_listings",
        "os_listing_variants",
        "os_sales_orders",
        "os_sales_order_items",
        "os_fulfillments",
        "os_settlement_lines",
        "os_learning_signals",
        "os_approval_requests",
        "os_operation_executions",
        "os_background_tasks",
        "os_sync_cursors",
        "os_audit_events",
    }
    assert expected <= names


def test_state_machines_reject_illegal_shortcuts():
    assert PRODUCT_STATES.can("review", "ready")
    assert not PRODUCT_STATES.can("draft", "active")
    assert LISTING_STATES.can("pending_approval", "publishing")
    assert not LISTING_STATES.can("draft", "active")
    assert FULFILLMENT_STATES.can("approved", "ordering")
    assert not FULFILLMENT_STATES.can("pending_approval", "ordered")
    with pytest.raises(ValueError):
        FULFILLMENT_STATES.require("pending_approval", "ordered")


def test_idempotency_key_is_stable_and_payload_sensitive():
    a = {"quantity": 1, "product": 7}
    b = {"product": 7, "quantity": 1}
    c = {"product": 7, "quantity": 2}
    assert payload_hash(a) == payload_hash(b)
    assert make_idempotency_key("supplier.order", "item", "1", a) == make_idempotency_key(
        "supplier.order", "item", "1", b
    )
    assert make_idempotency_key("supplier.order", "item", "1", a) != make_idempotency_key(
        "supplier.order", "item", "1", c
    )


def test_strict_supplier_contract_never_treats_unknown_as_free_or_unlimited():
    item = SupplierCatalogItem(
        supplier_code="sample",
        supplier_product_id="P1",
        name="검증 대기 상품",
        shipping_fee_krw=None,
        moq=None,
        variants=(
            SupplierCatalogVariant(
                supplier_variant_id="V1",
                option_key="size=270",
                supply_price_krw=50000,
                stock_qty=None,
            ),
        ),
    )
    errors = set(item.data_quality_errors())
    assert "SHIPPING_FEE_UNKNOWN" in errors
    assert "MOQ_UNKNOWN" in errors
    assert "STOCK_UNKNOWN:size=270" in errors
    assert "ONLINE_SALE_PERMISSION_UNKNOWN" in item.compliance_unknowns()
    assert "AUTHENTICITY_EVIDENCE_UNKNOWN" in item.compliance_unknowns()


def test_offer_verification_requires_all_order_critical_facts():
    row = OSOfferVerification(
        offer_id=1,
        price_known=True,
        shipping_fee_known=True,
        stock_known=True,
        moq_known=True,
        variant_identity_verified=False,
    )
    assert row.dropship_order_ready() is False
    row.variant_identity_verified = True
    assert row.dropship_order_ready() is True


def test_pending_listing_external_ids_are_unique_before_marketplace_publish():
    ensure_os_schema()
    with get_db() as db:
        p1 = OSProduct(sku="OSV3-PENDING-1", name="대기상품1")
        p2 = OSProduct(sku="OSV3-PENDING-2", name="대기상품2")
        db.add_all([p1, p2]); db.flush()
        l1 = OSListing(product_id=p1.id, platform="coupang", account_key="default")
        l2 = OSListing(product_id=p2.id, platform="coupang", account_key="default")
        db.add_all([l1, l2]); db.flush()
        assert l1.external_product_id.startswith("__pending__:")
        assert l2.external_product_id.startswith("__pending__:")
        assert l1.external_product_id != l2.external_product_id
        db.rollback()


def test_legacy_bridge_is_repeatable():
    first = migrate_legacy_to_os()
    second = migrate_legacy_to_os()
    assert first["ok"] is True
    assert second["ok"] is True
    assert first["products"] == second["products"]
    health = get_os_health()
    assert health["products"] == first["products"]


def test_production_control_plane_requires_token(monkeypatch):
    import app.os.api as api

    monkeypatch.delenv("SELLER_API_TOKEN", raising=False)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(env="production"))
    with pytest.raises(HTTPException) as exc:
        api._require_control_token(None)
    assert exc.value.status_code == 503

    monkeypatch.setenv("SELLER_API_TOKEN", "secret-token")
    with pytest.raises(HTTPException) as exc:
        api._require_control_token("Bearer wrong")
    assert exc.value.status_code == 401
    api._require_control_token("Bearer secret-token")


def test_normal_seller_os_ui_does_not_own_threads_orm_or_external_mutations():
    root = Path(__file__).resolve().parents[1]
    page = (root / "gui/pages/00_AutoSeller_Main.py").read_text(encoding="utf-8")
    workspace = (root / "gui/seller_os_v3.py").read_text(encoding="utf-8")
    entrypoint = (root / "gui/main.py").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")

    assert "services.background_jobs" not in page
    assert "from app.pipeline" not in page
    assert "sqlalchemy" not in page.lower()
    assert "execute_listing_publish" not in workspace
    assert 'queue_name="dangerous"' in workspace
    assert "legacy_app" not in entrypoint
    assert not (root / "gui/app.py").exists()
    assert 'streamlit", "run", "gui/main.py"' in dockerfile
    assert 'page_link("main.py"' in entrypoint
    assert "seller-dangerous-worker" in compose
    assert "오늘 할 일" in workspace
    assert "주문 · 배송" in workspace
    assert "설정 · 자동화" in workspace


def test_sourcing_import_is_immediately_routed_into_seller_os():
    root = Path(__file__).resolve().parents[1]
    page = (root / "gui/pages/30_상품소싱.py").read_text(encoding="utf-8")
    service = (root / "app/os/sourcing.py").read_text(encoding="utf-8")

    assert "from app.pipeline import import_product" not in page
    assert "from app.os.sourcing import import_supplier_product" in page
    assert "import_supplier_product(" in page
    assert "Seller OS > 상품에서 확인" in page
    assert "migrate_legacy_to_os()" in service
    assert "OSProduct" in service
