from app.services.data_graph import MarketplaceIdentity, ensure_data_graph_schema
from app.services.procurement_safety import inventory_replenishment_enabled


def test_marketplace_identity_model_is_canonical_bridge():
    assert MarketplaceIdentity.__tablename__ == "marketplace_identities"
    assert {"product_id", "listing_id", "platform", "identity_type", "identity_value"}.issubset(
        set(MarketplaceIdentity.__table__.columns.keys())
    )


def test_data_graph_schema_can_be_created():
    ensure_data_graph_schema()


def test_inventory_replenishment_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INVENTORY_REPLENISHMENT_ENABLED", raising=False)
    assert inventory_replenishment_enabled() is False
