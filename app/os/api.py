"""Seller OS v3 control-plane API.

The API is the stable application boundary for the current Streamlit UI and future
frontends. It never exposes direct ORM writes or synchronous external mutations.
"""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.image_studio.api import router as image_studio_router
from app.image_studio.models import ensure_image_studio_schema
from app.orchestration.campaign_director_api import router as campaign_director_router
from app.orchestration.campaign_director_models import ensure_campaign_director_schema
from app.orchestration.product_growth_api import router as product_growth_router
from app.orchestration.product_growth_models import ensure_product_growth_schema
from app.os.approvals import decide_approval, get_pending_approvals
from app.os.bridge import migrate_legacy_to_os
from app.os.dashboard import get_dashboard, list_orders, list_products
from app.os.operations import approve_fulfillment_state, request_listing_publish, request_order_fulfillment
from app.os.runtime_health import get_runtime_health
from app.os.schema import ensure_os_schema, get_os_health
from app.os.tasks import enqueue_task, get_task, list_tasks
from app.social.threads.migrations import ensure_threads_schema

app = FastAPI(title="AutoSellerAI Seller OS API", version="3.3")


def _require_control_token(authorization: str | None = Header(default=None)) -> None:
    """Protect the control plane when SELLER_API_TOKEN is configured.

    Local single-PC mode may omit the token because Docker binds the API to
    localhost. Non-local environments must explicitly configure a token.
    """
    expected = str(os.getenv("SELLER_API_TOKEN", "") or "").strip()
    env = str(get_settings().env or "local").strip().lower()
    if not expected:
        if env not in {"local", "dev", "development", "test"}:
            raise HTTPException(status_code=503, detail="SELLER_API_TOKEN이 설정되지 않았습니다.")
        return
    supplied = str(authorization or "")
    prefix = "Bearer "
    if not supplied.startswith(prefix) or not hmac.compare_digest(supplied[len(prefix):], expected):
        raise HTTPException(status_code=401, detail="유효한 Seller OS API 토큰이 필요합니다.")


router = APIRouter(prefix="/api/v3", dependencies=[Depends(_require_control_token)])


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
    ensure_image_studio_schema()
    ensure_threads_schema()
    ensure_product_growth_schema()
    ensure_campaign_director_schema()


@app.get("/health")
def health() -> dict:
    runtime = get_runtime_health()
    return {
        "ok": runtime["ok"],
        "ready": runtime["ready"],
        "status": runtime["status"],
        "os": get_os_health(),
        "runtime": runtime,
    }


@router.get("/dashboard")
def dashboard() -> dict:
    return get_dashboard()


@router.get("/products")
def products(status: str = "", keyword: str = "", limit: int = 100) -> list[dict]:
    return list_products(status=status, keyword=keyword, limit=limit)


@router.get("/orders")
def orders(status: str = "", limit: int = 100) -> list[dict]:
    return list_orders(status=status, limit=limit)


@router.get("/approvals")
def approvals(limit: int = 100) -> list[dict]:
    return get_pending_approvals(limit=limit)


@router.post("/approvals/{approval_id}/decision")
def approval_decision(approval_id: int, body: ApprovalDecision) -> dict:
    result = decide_approval(approval_id, approve=body.approve, actor=body.actor)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "승인 처리 실패"))
    return result


@router.post("/listings/request")
def listing_request(body: ListingRequest) -> dict:
    result = request_listing_publish(body.product_id, body.platform, actor=body.actor)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "등록 요청 실패"))
    return result


@router.post("/listings/execute/{approval_id}")
def listing_execute(approval_id: int) -> dict:
    """Queue an already-approved listing mutation; never execute it in HTTP lifecycle."""
    result = enqueue_task(
        "listing_publish",
        {"approval_id": int(approval_id)},
        queue_name="dangerous",
        dedupe_key=f"listing_publish:{int(approval_id)}",
    )
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error", "등록 작업 큐 실패"))
    return result


@router.post("/fulfillments/request")
def fulfillment_request(body: FulfillmentRequest) -> dict:
    result = request_order_fulfillment(body.order_item_id, actor=body.actor)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "발주 승인 요청 실패"))
    return result


@router.post("/fulfillments/approve-state/{approval_id}")
def fulfillment_approve_state(approval_id: int) -> dict:
    result = approve_fulfillment_state(approval_id)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "발주 상태 처리 실패"))
    return result


@router.post("/fulfillments/execute/{approval_id}")
def fulfillment_execute(approval_id: int) -> dict:
    """Queue a supplier order on the isolated dangerous worker.

    The worker independently rechecks approval, commercial facts, quantity/cost,
    stock, idempotency and the verified SupplierOrderPort driver before any API call.
    """
    result = enqueue_task(
        "supplier_order",
        {"approval_id": int(approval_id)},
        queue_name="dangerous",
        dedupe_key=f"supplier_order:{int(approval_id)}",
    )
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error", "공급처 발주 작업 큐 실패"))
    return result


@router.post("/tasks")
def task_enqueue(body: TaskRequest) -> dict:
    # Dangerous tasks still re-validate their approval inside the worker.
    result = enqueue_task(body.task_type, body.payload, queue_name=body.queue_name, dedupe_key=body.dedupe_key)
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error", "작업 큐 실패"))
    return result


@router.get("/tasks")
def tasks(limit: int = 50) -> list[dict]:
    return list_tasks(limit=limit)


@router.get("/tasks/{task_id}")
def task(task_id: int) -> dict:
    result = get_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="작업 없음")
    return result


@router.post("/migrations/legacy-bridge")
def legacy_bridge() -> dict:
    return migrate_legacy_to_os()


router.include_router(image_studio_router)
router.include_router(product_growth_router)
router.include_router(campaign_director_router)
app.include_router(router)
