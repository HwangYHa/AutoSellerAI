"""Lock-safe entrypoint for the marketplace SEO optimizer."""
from __future__ import annotations

import runpy
from pathlib import Path

from app.seo.market_safe_runtime import install_market_seo_safe_writes

install_market_seo_safe_writes()

runpy.run_path(
    str(Path(__file__).with_name("08_마켓_SEO_최적화.py")),
    run_name="__main__",
)
