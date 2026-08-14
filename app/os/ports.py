"""Seller OS integration ports.

Connectors translate external APIs into these contracts. Application services must
not depend on supplier/marketplace-specific payloads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class SupplierOrderCommand:
    order_item_id: int
    supplier_product_id: str
    supplier_variant_id: str
    quantity: int
    receiver_name: str
    receiver_phone: str
    address: str
    shipping_message: str = ""
    idempotency_key: str = ""


@dataclass(frozen=True)
class SupplierOrderResult:
    ok: bool
    supplier_order_id: str = ""
    status: str = ""
    amount_krw: int = 0
    delivery_company: str = ""
    tracking_number: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass(frozen=True)
class TrackingResult:
    ok: bool
    status: str = ""
    delivery_company: str = ""
    tracking_number: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@runtime_checkable
class SupplierOrderPort(Protocol):
    supplier_code: str

    def can_create_order(self) -> bool: ...
    def validate(self, command: SupplierOrderCommand) -> list[str]: ...
    def simulate(self, command: SupplierOrderCommand) -> dict[str, Any]: ...
    def create_order(self, command: SupplierOrderCommand, simulation: dict[str, Any] | None = None) -> SupplierOrderResult: ...
    def cancel_order(self, supplier_order_id: str, reason: str) -> SupplierOrderResult: ...
    def get_tracking(self, supplier_order_id: str) -> TrackingResult: ...


@dataclass(frozen=True)
class ListingPublishCommand:
    product_id: int
    platform: str
    payload: dict[str, Any]
    idempotency_key: str = ""


@dataclass(frozen=True)
class ListingPublishResult:
    ok: bool
    external_product_id: str = ""
    external_items: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@runtime_checkable
class MarketplaceMutationPort(Protocol):
    platform: str

    def publish(self, command: ListingPublishCommand) -> ListingPublishResult: ...
    def register_tracking(self, external_order_item_id: str, delivery_company: str, tracking_number: str) -> dict[str, Any]: ...
