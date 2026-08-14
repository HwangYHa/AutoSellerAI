"""Seller OS v3 operating kernel.

The OS package is the canonical application layer for AutoSellerAI.
Legacy modules remain infrastructure/compatibility code until their callers are migrated.
"""

from app.os.database import configure_database

# Configure the shared SQLAlchemy runtime before any application service asks for
# an engine/session. Local uses SQLite; production may supply DATABASE_URL.
configure_database()

from app.os.schema import ensure_os_schema  # noqa: E402

__all__ = ["ensure_os_schema"]
