"""AutoSellerAI application package."""

from app.sqlite_runtime import install_sqlite_runtime

install_sqlite_runtime()

# Install the marketplace SEO lock-safe persistence methods at package startup
# without running any schema DDL. This protects every entry path (including a
# direct Streamlit page URL) while avoiding concurrent create_all races when all
# Docker services start at the same time.
from app.seo import market_safe_runtime as _market_safe_runtime
from app.seo.market_optimizer import MarketSeoOptimizer as _MarketSeoOptimizer

if not getattr(_MarketSeoOptimizer, "_sqlite_safe_writes_installed", False):
    _MarketSeoOptimizer._persist = _market_safe_runtime._persist
    _MarketSeoOptimizer.approve_fields = _market_safe_runtime._approve_fields
    _MarketSeoOptimizer.apply_audit = _market_safe_runtime._apply_audit
    _MarketSeoOptimizer.apply_many = _market_safe_runtime._apply_many
    _MarketSeoOptimizer._sqlite_safe_writes_installed = True
