"""Approval gates and idempotent external-operation journal.

Dangerous actions (marketplace publish/update/delete, supplier order/cancel, paid AI)
must create an approval before execution.  The operation journal guarantees that a
logical action is executed at most once for a given idempotency key.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Callable

from app.db import get_db
from app.os.models import OSAuditEvent, OSApprovalRequest, OSOperationExecution
from app.os.schema import ensure_os_schema
from app.os.state import APPROVAL_STATES


def _json(data: Any) -> str:
    return json.dumps(data if data is not None else {}, ensure_ascii=False, sort_keys=True, default=str)


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def make_idempotency_key(action_type: str, entity_type: str, entity_id: str, payload: dict[str, Any]) -> str:
    raw = f"{action_type}|{entity_type}|{entity_id}|{payload_hash(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def request_approval(
    *,
    action_type: str,
    entity_type: str,
    entity_id: str | int,
    payload: dict[str, Any],
    summary: str,
    risk_level: str = "high",
    requested_by: str = "user",
    ttl_minutes: int = 60,
) -> dict[str, Any]:
    ensure_os_schema()
    entity_id_s = str(entity_id)
    digest = payload_hash(payload)
    now = datetime.utcnow()
    with get_db() as db:
        existing = (
            db.query(OSApprovalRequest)
            .filter_by(
                action_type=action_type,
                entity_type=entity_type,
                entity_id=entity_id_s,
                payload_hash=digest,
                status="pending",
            )
            .order_by(OSApprovalRequest.id.desc())
            .first()
        )
        if existing and (not existing.expires_at or existing.expires_at > now):
            return {"ok": True, "approval_id": existing.id, "status": existing.status, "reused": True}

        row = OSApprovalRequest(
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id_s,
            payload_hash=digest,
            payload_json=_json(payload),
            summary=summary[:500],
            risk_level=risk_level,
            status="pending",
            requested_by=requested_by,
            requested_at=now,
            expires_at=now + timedelta(minutes=max(5, int(ttl_minutes))),
        )
        db.add(row)
        db.flush()
        db.add(OSAuditEvent(
            actor=requested_by,
            action="approval.requested",
            entity_type="approval",
            entity_id=str(row.id),
            data_json=_json({"action_type": action_type, "target": f"{entity_type}:{entity_id_s}"}),
        ))
        db.commit()
        return {"ok": True, "approval_id": row.id, "status": "pending", "reused": False}


def decide_approval(approval_id: int, *, approve: bool, actor: str = "user") -> dict[str, Any]:
    ensure_os_schema()
    now = datetime.utcnow()
    with get_db() as db:
        row = db.query(OSApprovalRequest).filter_by(id=int(approval_id)).first()
        if not row:
            return {"ok": False, "error": "승인 요청을 찾을 수 없습니다."}
        if row.status != "pending":
            return {"ok": False, "error": f"이미 처리된 승인 요청입니다: {row.status}"}
        if row.expires_at and row.expires_at <= now:
            APPROVAL_STATES.require(row.status, "expired")
            row.status = "expired"
            row.decided_at = now
            row.decided_by = "system"
            db.commit()
            return {"ok": False, "error": "승인 요청의 유효시간이 만료되었습니다."}
        target = "approved" if approve else "rejected"
        APPROVAL_STATES.require(row.status, target)
        row.status = target
        row.decided_at = now
        row.decided_by = actor
        db.add(OSAuditEvent(
            actor=actor,
            action=f"approval.{target}",
            entity_type="approval",
            entity_id=str(row.id),
            data_json="{}",
        ))
        db.commit()
        return {"ok": True, "approval_id": row.id, "status": target}


def get_pending_approvals(limit: int = 100) -> list[dict[str, Any]]:
    ensure_os_schema()
    now = datetime.utcnow()
    with get_db() as db:
        # expire stale approvals before returning the work queue
        stale = db.query(OSApprovalRequest).filter(
            OSApprovalRequest.status == "pending",
            OSApprovalRequest.expires_at.is_not(None),
            OSApprovalRequest.expires_at <= now,
        ).all()
        for row in stale:
            row.status = "expired"
            row.decided_at = now
            row.decided_by = "system"
        if stale:
            db.commit()
        rows = (
            db.query(OSApprovalRequest)
            .filter_by(status="pending")
            .order_by(OSApprovalRequest.requested_at.asc())
            .limit(max(1, int(limit)))
            .all()
        )
        return [
            {
                "id": x.id,
                "action_type": x.action_type,
                "entity_type": x.entity_type,
                "entity_id": x.entity_id,
                "summary": x.summary,
                "risk_level": x.risk_level,
                "requested_at": x.requested_at,
                "expires_at": x.expires_at,
            }
            for x in rows
        ]


def execute_idempotent(
    *,
    action_type: str,
    entity_type: str,
    entity_id: str | int,
    payload: dict[str, Any],
    executor: Callable[[], Any],
    approval_id: int | None = None,
    require_approval: bool = True,
    actor: str = "system",
) -> dict[str, Any]:
    """Execute one side effect exactly once for the logical payload.

    A previously succeeded operation returns the stored response without invoking
    the external executor again.  Failed operations may be retried only by changing
    the payload (new idempotency key) or explicitly creating a new operation flow.
    """
    ensure_os_schema()
    entity_id_s = str(entity_id)
    key = make_idempotency_key(action_type, entity_type, entity_id_s, payload)

    with get_db() as db:
        existing = db.query(OSOperationExecution).filter_by(idempotency_key=key).first()
        if existing:
            try:
                response = json.loads(existing.response_json or "{}")
            except Exception:
                response = {}
            return {
                "ok": existing.status == "succeeded",
                "status": existing.status,
                "operation_id": existing.id,
                "reused": True,
                "response": response,
                "error": existing.error,
            }

        approval = None
        if require_approval:
            if not approval_id:
                return {"ok": False, "error": "위험 작업에는 승인 ID가 필요합니다."}
            approval = db.query(OSApprovalRequest).filter_by(id=int(approval_id)).first()
            if not approval or approval.status != "approved":
                return {"ok": False, "error": "승인되지 않은 작업입니다."}
            if approval.payload_hash != payload_hash(payload):
                return {"ok": False, "error": "승인한 내용과 실행할 내용이 다릅니다."}
            if approval.expires_at and approval.expires_at <= datetime.utcnow():
                return {"ok": False, "error": "승인 유효시간이 만료되었습니다."}

        op = OSOperationExecution(
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id_s,
            idempotency_key=key,
            approval_id=approval.id if approval else None,
            status="running",
            request_json=_json(payload),
            started_at=datetime.utcnow(),
        )
        db.add(op)
        db.flush()
        operation_id = op.id
        db.commit()

    try:
        result = executor()
        response_json = _json(result)
    except Exception as exc:
        with get_db() as db:
            op = db.query(OSOperationExecution).filter_by(id=operation_id).first()
            if op:
                op.status = "failed"
                op.error = f"{type(exc).__name__}: {exc}"
                op.finished_at = datetime.utcnow()
                db.add(OSAuditEvent(
                    actor=actor,
                    action="operation.failed",
                    entity_type=entity_type,
                    entity_id=entity_id_s,
                    data_json=_json({"operation_id": operation_id, "action_type": action_type, "error": op.error}),
                ))
                db.commit()
        return {"ok": False, "status": "failed", "operation_id": operation_id, "error": str(exc)}

    with get_db() as db:
        op = db.query(OSOperationExecution).filter_by(id=operation_id).first()
        if op:
            op.status = "succeeded"
            op.response_json = response_json
            op.finished_at = datetime.utcnow()
        if approval_id:
            approval = db.query(OSApprovalRequest).filter_by(id=int(approval_id)).first()
            if approval and approval.status == "approved":
                APPROVAL_STATES.require(approval.status, "consumed")
                approval.status = "consumed"
        db.add(OSAuditEvent(
            actor=actor,
            action="operation.succeeded",
            entity_type=entity_type,
            entity_id=entity_id_s,
            data_json=_json({"operation_id": operation_id, "action_type": action_type}),
        ))
        db.commit()
    try:
        response = json.loads(response_json)
    except Exception:
        response = {"value": str(result)}
    return {"ok": True, "status": "succeeded", "operation_id": operation_id, "reused": False, "response": response}
