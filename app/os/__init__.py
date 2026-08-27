"""Seller OS operating kernel.

The OS package is the canonical application layer for AutoSellerAI.
Legacy modules remain infrastructure/compatibility code until their callers are migrated.
"""

from app.os.database import configure_database

# Configure the shared SQLAlchemy runtime before any application service asks for
# an engine/session. Local uses SQLite; production may supply DATABASE_URL.
configure_database()

from app.os.schema import ensure_os_schema  # noqa: E402
from app.os.channel_template_runtime import install_channel_template_runtime  # noqa: E402
from app.os.commerce_runtime_v4 import install_commerce_runtime_v4  # noqa: E402

# Apply reusable channel templates first, then harden the final marketplace adapter
# boundary with the current production API contracts. Both installers are idempotent.
install_channel_template_runtime()
install_commerce_runtime_v4()

__all__ = ["ensure_os_schema"]
