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


@dataclass(frozen=True)
class PaymentPreparationResult:
    """Result of preparing a supplier payment without completing user authorization."""
    ok: bool
    payment_mode: str = "unknown"
    payment_url: str = ""
    external_payment_id: str = ""
    expected_amount_krw: int = 0
    user_action_required: bool = False
    supplier_order_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass(frozen=True)
class PaymentStatusResult:
    ok: bool
    status: str = ""  # awaiting_user | authorizing | paid | failed | expired | cancelled | refunded
    amount_krw: int = 0
    supplier_order_id: str = ""
    external_payment_id: str = ""
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


@runtime_checkable
class SupplierPaymentPort(Protocol):
    """Optional supplier payment capability.

    Drivers that require a card-app/user authorization implement this separately
    from SupplierOrderPort so order creation is never confused with payment completion.
    """
    supplier_code: str

    def prepare_payment(
        self,
        command: SupplierOrderCommand,
        *,
        simulation: dict[str, Any] | None = None,
    ) -> PaymentPreparationResult: ...

    def get_payment_status(
        self,
        external_payment_id: str,
        *,
        supplier_order_id: str = "",
    ) -> PaymentStatusResult: ...


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
