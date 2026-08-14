"""Explicit Seller OS domain state machines.

UI code must not invent statuses.  External integration code may report a raw
status, but application services translate it into one of these canonical states.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateMachine:
    transitions: dict[str, frozenset[str]]

    def can(self, current: str, target: str) -> bool:
        return target in self.transitions.get(current, frozenset())

    def require(self, current: str, target: str) -> None:
        if current == target:
            return
        if not self.can(current, target):
            raise ValueError(f"허용되지 않은 상태 전이: {current} -> {target}")


PRODUCT_STATES = StateMachine({
    "draft": frozenset({"review", "archived"}),
    "review": frozenset({"draft", "ready", "archived"}),
    "ready": frozenset({"review", "active", "paused", "archived"}),
    "active": frozenset({"paused", "archived"}),
    "paused": frozenset({"active", "archived"}),
    "archived": frozenset(),
})

LISTING_STATES = StateMachine({
    "draft": frozenset({"pending_approval", "archived"}),
    "pending_approval": frozenset({"draft", "publishing", "archived"}),
    "publishing": frozenset({"active", "failed"}),
    "active": frozenset({"paused", "failed", "archived"}),
    "paused": frozenset({"active", "archived"}),
    "failed": frozenset({"draft", "pending_approval", "archived"}),
    "archived": frozenset(),
})

ORDER_STATES = StateMachine({
    "new": frozenset({"exception", "ready_to_fulfill", "cancelled"}),
    "exception": frozenset({"ready_to_fulfill", "cancelled"}),
    "ready_to_fulfill": frozenset({"fulfilling", "exception", "cancelled"}),
    "fulfilling": frozenset({"shipped", "exception", "cancelled"}),
    "shipped": frozenset({"completed", "exception"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
})

ORDER_ITEM_STATES = StateMachine({
    "new": frozenset({"exception", "ready", "cancelled"}),
    "exception": frozenset({"ready", "cancelled"}),
    "ready": frozenset({"approved", "exception", "cancelled"}),
    "approved": frozenset({"ordered", "exception", "cancelled"}),
    "ordered": frozenset({"shipped", "exception", "cancelled"}),
    "shipped": frozenset({"completed", "exception"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
})

FULFILLMENT_STATES = StateMachine({
    "pending_approval": frozenset({"approved", "cancelled"}),
    "approved": frozenset({"ordering", "cancelled"}),
    "ordering": frozenset({"ordered", "failed"}),
    "ordered": frozenset({"shipping", "shipped", "failed", "cancelled"}),
    "shipping": frozenset({"shipped", "failed"}),
    "shipped": frozenset({"completed", "failed"}),
    "completed": frozenset(),
    "failed": frozenset({"pending_approval", "cancelled"}),
    "cancelled": frozenset(),
})

APPROVAL_STATES = StateMachine({
    "pending": frozenset({"approved", "rejected", "expired", "cancelled"}),
    "approved": frozenset({"consumed", "cancelled", "expired"}),
    "rejected": frozenset(),
    "consumed": frozenset(),
    "expired": frozenset(),
    "cancelled": frozenset(),
})
