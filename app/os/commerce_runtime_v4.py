"""Production marketplace runtime hardening for Seller OS v4.

This module keeps the legacy public interfaces intact while correcting marketplace
mutation behavior that differs from the current official Coupang/Naver contracts.
It is intentionally installed after channel_template_runtime so reusable templates
reach the final create_product payload boundary.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import urlparse

import httpx

_INSTALLED = False


def _ok_response(response: httpx.Response) -> dict[str, Any]:
    ok = response.status_code in (200, 201, 204)
    try:
        data: Any = response.json() if response.content else {}
    except Exception:
        data = {"text": response.text[:1000]}
    return {
        "ok": ok,
        "status_code": response.status_code,
        "data": data,
        "error": "" if ok else response.text[:1000],
    }


def _coupang_put_no_body(uploader: Any, path: str, query: str = "") -> dict[str, Any]:
    url = f"{uploader.__class__.__module__ and 'https://api-gateway.coupang.com'}{path}"
    if query:
        url += f"?{query}"
    response = httpx.put(
        url,
        headers=uploader._sign("PUT", urlparse(path).path, query),
        timeout=30,
    )
    return _ok_response(response)


def _coupang_update_stock(self: Any, vendor_item_id: str, qty: int) -> dict[str, Any]:
    """Use Coupang's approved-item quantity API and keep sale state in sync.

    qty <= 0 means a real marketplace sold-out: quantity is set to zero and the
    vendor item is also stopped. qty > 0 restores quantity first, then resumes sale.
    """
    item_id = str(vendor_item_id).strip()
    quantity = max(0, int(qty))
    if not item_id:
        return {"ok": False, "error": "vendorItemId가 비어 있습니다."}

    quantity_result = _coupang_put_no_body(
        self,
        f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{item_id}/quantities/{quantity}",
    )
    if not quantity_result.get("ok"):
        return quantity_result

    state_path = (
        f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{item_id}/sales/stop"
        if quantity <= 0
        else f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{item_id}/sales/resume"
    )
    state_result = _coupang_put_no_body(self, state_path)
    return {
        "ok": bool(state_result.get("ok")),
        "quantity": quantity_result,
        "sale_state": state_result,
        "error": state_result.get("error", "") if not state_result.get("ok") else "",
    }


def _coupang_update_price(self: Any, vendor_item_id: str, price: int) -> dict[str, Any]:
    item_id = str(vendor_item_id).strip()
    normalized = max(10, (int(price) // 10) * 10)
    if not item_id:
        return {"ok": False, "error": "vendorItemId가 비어 있습니다."}
    return _coupang_put_no_body(
        self,
        f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{item_id}/prices/{normalized}",
        "forceSalePriceUpdate=true",
    )


@contextmanager
def _temporary_attrs(obj: Any, updates: dict[str, Any]) -> Iterator[None]:
    before: dict[str, Any] = {}
    for attr, value in updates.items():
        if value in (None, ""):
            continue
        before[attr] = getattr(obj, attr, None)
        setattr(obj, attr, value)
    try:
        yield
    finally:
        for attr, value in before.items():
            setattr(obj, attr, value)


def _wrap_coupang_create(original: Any) -> Any:
    if getattr(original, "_autoseller_v4_wrapped", False):
        return original

    def wrapped(self: Any, product: dict[str, Any]) -> dict[str, Any]:
        p = dict(product)
        updates: dict[str, Any] = {}
        if p.get("delivery_company_code"):
            from app.platforms.coupang import _normalize_delivery_code
            updates["_delivery_code"] = _normalize_delivery_code(str(p["delivery_company_code"]))
        if p.get("return_fee") not in (None, ""):
            updates["_return_charge"] = max(0, int(p["return_fee"]))
        if p.get("as_phone"):
            updates["_contact"] = str(p["as_phone"]).strip()
        with _temporary_attrs(self, updates):
            return original(self, p)

    wrapped._autoseller_v4_wrapped = True  # type: ignore[attr-defined]
    return wrapped


def _wrap_smartstore_create(original: Any) -> Any:
    if getattr(original, "_autoseller_v4_wrapped", False):
        return original

    def wrapped(self: Any, product: dict[str, Any]) -> dict[str, Any]:
        p = dict(product)
        category = str(p.get("category") or "").strip()
        if category.isdigit():
            # SmartStoreUploader resolves CATEGORY_MAP keys. Registering the explicit
            # leafCategoryId makes cross-market clone/bulk import deterministic.
            from app.platforms.smartstore import CATEGORY_MAP
            CATEGORY_MAP[category] = category

        updates: dict[str, Any] = {}
        if p.get("delivery_company_code"):
            updates["_delivery_code"] = str(p["delivery_company_code"]).strip()
        if p.get("as_phone"):
            updates["_after_service_phone"] = str(p["as_phone"]).strip()
        with _temporary_attrs(self, updates):
            return original(self, p)

    wrapped._autoseller_v4_wrapped = True  # type: ignore[attr-defined]
    return wrapped


def install_commerce_runtime_v4() -> None:
    """Install idempotent runtime fixes without changing caller-facing APIs."""
    global _INSTALLED
    if _INSTALLED:
        return

    from app.platforms.coupang import CoupangUploader
    from app.platforms.smartstore import SmartStoreUploader

    # Official approved-item mutation endpoints.
    CoupangUploader.update_vendor_item_stock = _coupang_update_stock
    CoupangUploader.update_product_price = _coupang_update_price

    # Channel template values must affect the concrete marketplace payload, not only
    # a local intermediate dictionary.
    CoupangUploader.create_product = _wrap_coupang_create(CoupangUploader.create_product)
    SmartStoreUploader.create_product = _wrap_smartstore_create(SmartStoreUploader.create_product)

    _INSTALLED = True
