"""AutoSellerAI application package."""

from app.sqlite_runtime import install_sqlite_runtime

install_sqlite_runtime()

# Install the marketplace SEO lock-safe persistence methods at package startup.
# This protects every entry path, including direct navigation to the original
# Streamlit SEO page, background imports, tests, and the safe wrapper page.
from app.seo.market_safe_runtime import install_market_seo_safe_writes

install_market_seo_safe_writes()
