from uuid import uuid4

from app.db import get_db
from app.services.data_graph import MarketplaceIdentity, _upsert_identity, ensure_data_graph_schema


def test_marketplace_identity_upsert_is_idempotent_and_updates_existing_row():
    ensure_data_graph_schema()
    value = f"test-{uuid4().hex}"

    with get_db() as db:
        assert _upsert_identity(
            db,
            product_id=101,
            listing_id=201,
            platform="coupang",
            identity_type="vendor_item_id",
            identity_value=value,
        )
        db.commit()

    with get_db() as db:
        # The same marketplace identity must be reusable instead of raising UNIQUE.
        assert _upsert_identity(
            db,
            product_id=102,
            listing_id=202,
            platform="coupang",
            identity_type="vendor_item_id",
            identity_value=value,
        )
        db.commit()

    with get_db() as db:
        rows = db.query(MarketplaceIdentity).filter_by(
            platform="coupang",
            identity_type="vendor_item_id",
            identity_value=value,
        ).all()
        assert len(rows) == 1
        assert rows[0].product_id == 102
        assert rows[0].listing_id == 202
        db.delete(rows[0])
        db.commit()
