"""Seller OS v3 control-plane API.

This is the stable application boundary for the current Streamlit UI and a future
React/Next.js frontend.  Business mutations must flow through application services,
not direct ORM writes from the UI.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.os.approvals import decide_approval, get_pending_approvals
from app.os.bridge import migrate_legacy_to_os
from app.os.dashboard import get_dashboard, list_orders, list_products
from app.os.operations import (
    approve_fulfillment_state,
    execute_listing_publish,
    request_listing_publish,
    request_order_fulfillment,
)
from app.os.schema import ensure_os_schema, get_os_health
from app.os.tasks import enqueue_task, get_task, list_tasks

app = FastAPI(title="AutoSellerAI Seller OS API", version="3.0")


class TaskRequest(BaseModel):
    task_type: str
    payload: dict = Field(default_factory=dict)
    queue_name: str = "sync"
    dedupe_key: str = ""


class ApprovalDecision(BaseModel):
    approve: bool
    actor: str = "user"


class ListingRequest(BaseModel):
    product_id: int
    platform: str
    actor: str = "user"


class FulfillmentRequest(BaseModel):
    order_item_id: int
    actor: str = "user"


@app.on_event("startup")
def _startup() -> None:
    ensure_os_schema()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "os": get_os_health()}


@app.get("/api/v3/dashboard")
def dashboard() -> dict:
    return get_dashboard()


@app.get("/api/v3/products")
def products(status: str = "", keyword: str = "", limit: int = 100) -> list[dict]:
    return list_products(status=status, keyword=keyword, limit=limit)


@app.get("/api/v3/orders")
def orders(status: str = "", limit: int = 100) -> list[dict]:
    return list_orders(status=status, limit=limit)


@app.get("/api/v3/approvals")
def approvals(limit: int = 100) -> list[dict]:
    return get_pending_approvals(limit=limit)


@app.post("/api/v3/approvals/{approval_id}/decision")
def approval_decision(approval_id: int, body: ApprovalDecision) -> dict:
    result = decide_approval(approval_id, approve=body.approve, actor=body.actor)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "승인 처리 실패"))
    return result


@app.post("/api/v3/listings/request")
def listing_request(body: ListingRequest) -> dict:
    result = request_listing_publish(body.product_id, body.platform, actor=body.actor)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "등록 요청 실패"))
    return result


@app.post("/api/v3/listings/execute/{approval_id}")
def listing_execute(approval_id: int, actor: str = "user") -> dict:
    result = execute_listing_publish(approval_id, actor=actor)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "등록 실행 실패"))
    return result


@app.post("/api/v3/fulfillments/request")
def fulfillment_request(body: FulfillmentRequest) -> dict:
    result = request_order_fulfillment(body.order_item_id, actor=body.actor)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "발주 승인 요청 실패"))
    return result


@app.post("/api/v3/fulfillments/approve-state/{approval_id}")
def fulfillment_approve_state(approval_id: int) -> dict:
    result = approve_fulfillment_state(approval_id)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "발주 상태 처리 실패"))
    return result


@app.post("/api/v3/tasks")
def task_enqueue(body: TaskRequest) -> dict:
    result = enqueue_task(
        body.task_type,
        body.payload,
        queue_name=body.queue_name,
        dedupe_key=body.dedupe_key,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error", "작업 큐 실패"))
    return result


@app.get("/api/v3/tasks")
def tasks(limit: int = 50) -> list[dict]:
    return list_tasks(limit=limit)


@app.get("/api/v3/tasks/{task_id}")
def task(task_id: int) -> dict:
    result = get_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="작업 없음")
    return result


@app.post("/api/v3/migrations/legacy-bridge")
def legacy_bridge() -> dict:
    # Read/reconcile only; no marketplace/supplier mutation.
    return migrate_legacy_to_os()
