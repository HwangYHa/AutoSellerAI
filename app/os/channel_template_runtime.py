"""Install channel-template application at the marketplace uploader boundary.

Legacy upload_product still constructs fallback shipping values.  Wrapping the two
uploader create_product methods here makes templates effective for every Seller OS
publish path without rewriting product truth fields or duplicating marketplace code.
"""
from __future__ import annotations

from functools import wraps
from typing import Any

_INSTALLED = False
_OPERATIONAL_KEYS = {
    "shipping_fee",
    "return_fee",
    "delivery_company_code",
    "free_ship_over_amount",
    "remote_area_deliverable",
    "as_phone",
    "as_information",
}


def _apply(product: dict[str, Any], platform: str) -> dict[str, Any]:
    from app.db import get_db
    from app.os.commerce_ops_models import OSChannelTemplate
    import json

    output = dict(product)
    with get_db() as db:
        rows = db.query(OSChannelTemplate).filter_by(platform=platform, enabled=True).order_by(OSChannelTemplate.id.asc()).all()
        if not rows:
            return output
        category = str(output.get("category") or "")
        chosen = next((x for x in rows if x.category_hint and x.category_hint in category), rows[0])
        try:
            values = json.loads(chosen.template_json or "{}")
        except Exception:
            values = {}
        if isinstance(values, dict):
            # Operational template settings override compatibility fallbacks such as
            # the legacy hard-coded 3000 won shipping fee. Product facts do not.
            for key, value in values.items():
                if key in _OPERATIONAL_KEYS and value not in (None, ""):
                    output[key] = value
        if not output.get("category") and chosen.category_hint:
            output["category"] = chosen.category_hint
        output["channel_template_id"] = chosen.id
        output["channel_template_name"] = chosen.name
    return output


def install_channel_template_runtime() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from app.platforms.coupang import CoupangUploader
    from app.platforms.smartstore import SmartStoreUploader

    for cls, platform in ((CoupangUploader, "coupang"), (SmartStoreUploader, "smartstore")):
        original = cls.create_product
        if getattr(original, "_autoseller_template_wrapped", False):
            continue

        @wraps(original)
        def wrapped(self, product, _original=original, _platform=platform):
            return _original(self, _apply(dict(product), _platform))

        wrapped._autoseller_template_wrapped = True  # type: ignore[attr-defined]
        cls.create_product = wrapped
    _INSTALLED = True
