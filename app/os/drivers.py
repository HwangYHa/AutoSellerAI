"""Verified external mutation driver registry.

A connector being able to authenticate or read data does NOT make it eligible for
automatic ordering.  Supplier order drivers must be explicitly registered as
verified after payload mapping, simulation, cancellation and tracking tests pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from app.os.ports import SupplierOrderPort


@dataclass(frozen=True)
class SupplierDriverRegistration:
    code: str
    driver: SupplierOrderPort
    verified: bool
    verification_note: str = ""


_lock = RLock()
_supplier_order_drivers: dict[str, SupplierDriverRegistration] = {}


def register_supplier_order_driver(
    code: str,
    driver: SupplierOrderPort,
    *,
    verified: bool = False,
    verification_note: str = "",
) -> None:
    code = str(code or "").strip().lower()
    if not code:
        raise ValueError("supplier code가 필요합니다.")
    if str(getattr(driver, "supplier_code", "")).strip().lower() != code:
        raise ValueError("driver.supplier_code와 등록 code가 다릅니다.")
    with _lock:
        _supplier_order_drivers[code] = SupplierDriverRegistration(
            code=code,
            driver=driver,
            verified=bool(verified),
            verification_note=verification_note,
        )


def get_supplier_order_driver(code: str, *, require_verified: bool = True) -> SupplierOrderPort | None:
    code = str(code or "").strip().lower()
    with _lock:
        row = _supplier_order_drivers.get(code)
    if not row:
        return None
    if require_verified and not row.verified:
        return None
    return row.driver


def supplier_driver_status(code: str) -> dict:
    code = str(code or "").strip().lower()
    with _lock:
        row = _supplier_order_drivers.get(code)
    if not row:
        return {"registered": False, "verified": False, "can_create_order": False, "note": "v3 주문 드라이버 미등록"}
    try:
        can_create = bool(row.driver.can_create_order())
    except Exception:
        can_create = False
    return {
        "registered": True,
        "verified": bool(row.verified),
        "can_create_order": bool(row.verified and can_create),
        "note": row.verification_note,
    }


def list_supplier_driver_status() -> list[dict]:
    with _lock:
        codes = sorted(_supplier_order_drivers)
    return [{"code": code, **supplier_driver_status(code)} for code in codes]
