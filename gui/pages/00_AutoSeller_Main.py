"""Run the preserved legacy AutoSellerAI workspace from its original gui/ path."""
from __future__ import annotations

import os
import runpy

runpy.run_path(
    os.path.join(os.path.dirname(__file__), "..", "legacy_app.py"),
    run_name="__main__",
)
