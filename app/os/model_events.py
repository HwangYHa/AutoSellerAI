"""ORM invariants that cannot be left to individual callers."""
from __future__ import annotations

from sqlalchemy import event

from app.os.models import OSListing


@event.listens_for(OSListing, "before_insert")
def _ensure_pending_listing_identity(mapper, connection, target: OSListing) -> None:  # noqa: ARG001
    """Avoid duplicate empty external IDs before a marketplace ID exists.

    A listing is unique by internal product/platform/account before publication.
    The marketplace external ID only exists after publication.  Using one shared
    empty string would violate the external-ID unique constraint as soon as two
    draft listings exist on the same platform.  A deterministic internal pending
    identity keeps the row valid until the real external ID replaces it.
    """
    if not str(target.external_product_id or "").strip():
        target.external_product_id = f"__pending__:{target.product_id}"
