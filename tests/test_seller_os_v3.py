from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect

from app.db import _get_engine, get_db
from app.os.approvals import make_idempotency_key, payload_hash
from app.os.bridge import migrate_legacy_to_os
from app.os.models import OSListing, OSProduct
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
    app = (root / "gui/app.py").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "services.background_jobs" not in page
    assert "from app.pipeline" not in page
    assert "sqlalchemy" not in page.lower()
    assert "execute_listing_publish" not in workspace
    assert 'queue_name="dangerous"' in workspace
    assert "legacy_app" not in app
    assert "seller-dangerous-worker" in compose
    assert "오늘 할 일" in workspace
    assert "주문 · 배송" in workspace
    assert "설정 · 자동화" in workspace
