"""공급사 워크플로우 엔진 (Supplier Workflow Engine).

[설계 원칙]
  - 공급사별로 상태 전이(State Transition) 규칙이 다름
  - 새 공급사 추가 = StateMachine 정의 1개만 등록
  - SupplierWorkflowItem DB 레코드로 모든 상태 이력 영속화

[공급사별 상태 흐름]

  도매꾹 / 도매매 (즉시 등록):
    DISCOVERED → AI_SCORED → CONTENT_GENERATED → LISTED
                           └→ REJECTED (점수 미달)

  온채널 (승인 필요):
    DISCOVERED → AI_SCORED → APPROVAL_PENDING → APPROVAL_REQUESTED
                           │                  → APPROVED → CONTENT_GENERATED → LISTED
                           │                  → REJECTED (재시도 가능)
                           └→ SKIPPED (점수 미달)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

logger = logging.getLogger(__name__)

# ── 워크플로우 상태 정의 ────────────────────────────────────────────────────────

class WFState:
    DISCOVERED          = "DISCOVERED"
    AI_SCORED           = "AI_SCORED"
    APPROVAL_PENDING    = "APPROVAL_PENDING"    # 온채널 전용
    APPROVAL_REQUESTED  = "APPROVAL_REQUESTED"  # 온채널 전용
    APPROVED            = "APPROVED"            # 온채널 전용
    CONTENT_GENERATED   = "CONTENT_GENERATED"
    LISTED              = "LISTED"
    REJECTED            = "REJECTED"
    SKIPPED             = "SKIPPED"


# ── 상태 머신 정의 ─────────────────────────────────────────────────────────────

@dataclass
class Transition:
    from_state: str
    to_state: str
    condition: str = ""     # 전이 조건 설명 (문서화용)


@dataclass
class StateMachine:
    supplier_id: str
    transitions: list[Transition]
    requires_approval: bool = False

    def allowed_next(self, current_state: str) -> list[str]:
        return [t.to_state for t in self.transitions if t.from_state == current_state]

    def can_transition(self, from_state: str, to_state: str) -> bool:
        return to_state in self.allowed_next(from_state)


# ── 공급사별 상태 머신 등록 ──────────────────────────────────────────────────────

_MACHINES: dict[str, StateMachine] = {

    "domeggook": StateMachine(
        supplier_id="domeggook",
        requires_approval=False,
        transitions=[
            Transition("DISCOVERED",        "AI_SCORED"),
            Transition("AI_SCORED",         "CONTENT_GENERATED",  "점수 >= 80"),
            Transition("AI_SCORED",         "REJECTED",           "점수 < 80"),
            Transition("CONTENT_GENERATED", "LISTED"),
            Transition("LISTED",            "REJECTED",           "플랫폼 등록 실패"),
        ],
    ),

    "domemai": StateMachine(
        supplier_id="domemai",
        requires_approval=False,
        transitions=[
            Transition("DISCOVERED",        "AI_SCORED"),
            Transition("AI_SCORED",         "CONTENT_GENERATED",  "점수 >= 80"),
            Transition("AI_SCORED",         "REJECTED",           "점수 < 80"),
            Transition("CONTENT_GENERATED", "LISTED"),
            Transition("LISTED",            "REJECTED",           "플랫폼 등록 실패"),
        ],
    ),

    "onchannel": StateMachine(
        supplier_id="onchannel",
        requires_approval=True,             # ← 핵심 차이
        transitions=[
            Transition("DISCOVERED",            "AI_SCORED"),
            Transition("AI_SCORED",             "APPROVAL_PENDING",   "점수 >= 80"),
            Transition("AI_SCORED",             "SKIPPED",            "점수 < 80"),
            Transition("APPROVAL_PENDING",      "APPROVAL_REQUESTED", "판매신청 완료"),
            Transition("APPROVAL_REQUESTED",    "APPROVED",           "공급사 승인"),
            Transition("APPROVAL_REQUESTED",    "REJECTED",           "공급사 거절"),
            Transition("REJECTED",              "APPROVAL_PENDING",   "재신청 (retry < max)"),
            Transition("APPROVED",              "CONTENT_GENERATED"),
            Transition("CONTENT_GENERATED",     "LISTED"),
        ],
    ),
}

# 새 공급사 추가용: 기본값 (즉시 등록 가능)
_DEFAULT_MACHINE = StateMachine(
    supplier_id="default",
    requires_approval=False,
    transitions=[
        Transition("DISCOVERED",        "AI_SCORED"),
        Transition("AI_SCORED",         "CONTENT_GENERATED", "점수 >= 80"),
        Transition("AI_SCORED",         "REJECTED",          "점수 < 80"),
        Transition("CONTENT_GENERATED", "LISTED"),
    ],
)


def get_machine(supplier_id: str) -> StateMachine:
    return _MACHINES.get(supplier_id, _DEFAULT_MACHINE)


def requires_approval(supplier_id: str) -> bool:
    return get_machine(supplier_id).requires_approval


# ── 워크플로우 아이템 CRUD ──────────────────────────────────────────────────────

def create_workflow_item(supplier_id: str, raw_id: str,
                          product_name: str, supply_price: float,
                          raw_product_id: int | None = None) -> "SupplierWorkflowItem":  # type: ignore
    """DISCOVERED 상태로 워크플로우 아이템을 생성한다."""
    from app.db import get_db, SupplierWorkflowItem

    with get_db() as db:
        existing = db.query(SupplierWorkflowItem).filter_by(
            supplier_id=supplier_id, raw_id=raw_id
        ).first()
        if existing:
            return existing

        item = SupplierWorkflowItem(
            supplier_id=supplier_id,
            raw_id=raw_id,
            product_name=product_name[:400],
            supply_price=supply_price,
            raw_product_id=raw_product_id,
            workflow_state=WFState.DISCOVERED,
            state_history=json.dumps([{
                "state": WFState.DISCOVERED,
                "ts": datetime.utcnow().isoformat(),
            }]),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item


def transition(item_id: int, to_state: str,
               error_msg: str = "", extra: dict | None = None) -> dict:
    """워크플로우 상태를 전이한다.

    Returns: {"ok": bool, "from": str, "to": str, "error": str}
    """
    from app.db import get_db, SupplierWorkflowItem

    with get_db() as db:
        item = db.query(SupplierWorkflowItem).filter_by(id=item_id).first()
        if not item:
            return {"ok": False, "error": f"워크플로우 아이템 없음: id={item_id}"}

        machine = get_machine(item.supplier_id)
        from_state = item.workflow_state

        if not machine.can_transition(from_state, to_state):
            allowed = machine.allowed_next(from_state)
            return {
                "ok": False,
                "from": from_state,
                "to": to_state,
                "error": f"허용되지 않은 전이 {from_state}→{to_state}. 허용: {allowed}",
            }

        # 이력 업데이트
        history = json.loads(item.state_history or "[]")
        history.append({
            "state": to_state,
            "ts": datetime.utcnow().isoformat(),
            **({"error": error_msg} if error_msg else {}),
            **(extra or {}),
        })

        item.workflow_state = to_state
        item.state_history = json.dumps(history, ensure_ascii=False)
        item.state_changed_at = datetime.utcnow()
        if error_msg:
            item.error_message = error_msg[:500]

        db.commit()
        logger.info("WF 전이 [%s/%s] %s → %s", item.supplier_id, item.raw_id, from_state, to_state)
        return {"ok": True, "from": from_state, "to": to_state}


def get_workflow_items(
    supplier_id: str = "",
    state: str = "",
    limit: int = 200,
) -> list[dict]:
    """워크플로우 아이템 목록 조회."""
    from app.db import get_db, SupplierWorkflowItem

    with get_db() as db:
        q = db.query(SupplierWorkflowItem)
        if supplier_id:
            q = q.filter(SupplierWorkflowItem.supplier_id == supplier_id)
        if state:
            q = q.filter(SupplierWorkflowItem.workflow_state == state)
        rows = q.order_by(SupplierWorkflowItem.updated_at.desc()).limit(limit).all()
        return [_wf_to_dict(r) for r in rows]


def get_workflow_stats() -> dict:
    """공급사별·상태별 집계."""
    from app.db import get_db, SupplierWorkflowItem
    from sqlalchemy import func

    with get_db() as db:
        rows = db.query(
            SupplierWorkflowItem.supplier_id,
            SupplierWorkflowItem.workflow_state,
            func.count(SupplierWorkflowItem.id).label("cnt"),
        ).group_by(
            SupplierWorkflowItem.supplier_id,
            SupplierWorkflowItem.workflow_state,
        ).all()

    stats: dict = {}
    for sid, state, cnt in rows:
        if sid not in stats:
            stats[sid] = {}
        stats[sid][state] = cnt

    # 온채널 퍼널 계산 추가
    if "onchannel" in stats:
        oc = stats["onchannel"]
        discovered = oc.get("DISCOVERED", 0)
        scored = oc.get("AI_SCORED", 0)
        pending = oc.get("APPROVAL_PENDING", 0)
        requested = oc.get("APPROVAL_REQUESTED", 0)
        approved = oc.get("APPROVED", 0)
        listed = oc.get("LISTED", 0)
        rejected = oc.get("REJECTED", 0)
        total_scored = scored + pending + requested + approved + listed + rejected
        stats["onchannel"]["_funnel"] = {
            "approval_request_rate": round(requested / max(total_scored, 1) * 100, 1),
            "approval_success_rate": round(approved / max(requested, 1) * 100, 1),
            "listing_rate": round(listed / max(approved, 1) * 100, 1),
        }

    return stats


def _wf_to_dict(item) -> dict:
    return {
        "id": item.id,
        "supplier_id": item.supplier_id,
        "raw_id": item.raw_id,
        "product_name": item.product_name,
        "supply_price": float(item.supply_price or 0),
        "workflow_state": item.workflow_state,
        "ai_score": float(item.ai_score or 0),
        "score_breakdown": json.loads(item.score_breakdown or "{}"),
        "approval_status": item.approval_status,
        "approval_retry_count": item.approval_retry_count,
        "approval_reject_reason": item.approval_reject_reason,
        "content_generated": item.content_generated,
        "product_id": item.product_id,
        "error_message": item.error_message,
        "state_changed_at": item.state_changed_at.strftime("%Y-%m-%d %H:%M") if item.state_changed_at else "",
        "state_history": json.loads(item.state_history or "[]"),
    }
