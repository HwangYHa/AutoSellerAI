"""AutoSellerAI 원큐 운영 플로우.

기존 15단계는 사용자가 실제로 해야 하는 판단 단위보다 잘게 쪼개져 있었다.
Seller OS v2에서는 아래 8개 업무 단계만 사용한다.

1 연결 점검
2 상품 확보·동기화
3 판매 준비(AI 선별/이미지/SEO/가격 통합)
4 판매채널 등록
5 주문 수집
6 발주·송장·배송
7 정산·실제 수익
8 마케팅·수익학습(선택)

조회/동기화처럼 되돌릴 수 있는 작업은 안전 자동실행에 포함하고,
실제 상품등록·공급처 발주처럼 외부 상태/비용을 바꾸는 작업은 승인 단계로 둔다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkflowStage:
    order: int
    key: str
    title: str
    description: str
    page: str
    optional: bool = False
    safe_auto: bool = False
    approval_required: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


WORKFLOW_STAGES: tuple[WorkflowStage, ...] = (
    WorkflowStage(1, "connections", "연결 점검", "판매채널·공급처·AI 인증 상태를 확인합니다.", "pages/00_AutoSeller_Main.py"),
    WorkflowStage(2, "acquire", "상품 확보 · 동기화", "공급처를 통합 검색하고 쿠팡·스마트스토어 기존상품을 내부 DB와 맞춥니다.", "pages/30_상품소싱.py", safe_auto=True),
    WorkflowStage(3, "prepare", "판매 준비", "AI 선별·대표/상세 이미지·SEO·판매가·예상수익 검증을 상품관리에서 한 번에 끝냅니다.", "pages/00_AutoSeller_Main.py", safe_auto=True),
    WorkflowStage(4, "listing", "판매채널 등록", "검수된 상품만 쿠팡·스마트스토어에 실제 등록합니다.", "pages/00_AutoSeller_Main.py", approval_required=True),
    WorkflowStage(5, "orders", "주문 수집", "쿠팡·스마트스토어 신규 주문을 Seller OS로 모읍니다.", "pages/00_AutoSeller_Main.py", safe_auto=True),
    WorkflowStage(6, "fulfillment", "발주 · 송장 · 배송", "주문/옵션/수취정보를 확인해 공급처에 발주하고 실제 송장을 판매채널로 돌려보냅니다.", "pages/00_AutoSeller_Main.py", approval_required=True),
    WorkflowStage(7, "settlement", "정산 · 실제 수익", "매출·공급가·수수료·배송·광고·반품·세금을 합쳐 실제 순이익을 확인합니다.", "pages/00_AutoSeller_Main.py"),
    WorkflowStage(8, "growth", "마케팅 · 수익 학습", "스레드 콘텐츠와 구매귀속 데이터를 실제 순이익에 연결해 다음 판매 전략에 반영합니다.", "pages/10_Social_Commerce_Threads.py", optional=True, safe_auto=True),
)


def _count(db, model, **filters) -> int:
    q = db.query(model)
    if filters:
        q = q.filter_by(**filters)
    return int(q.count())


def _valid_naver_commerce_secret(value: str) -> bool:
    secret = (value or "").strip().strip('"').strip("'")
    if secret.startswith("$$"):
        secret = secret.replace("$$", "$")
    return len(secret) == 29 and secret.startswith(("$2a$", "$2b$", "$2y$"))


def _connection_state() -> dict[str, Any]:
    try:
        from app.config import get_settings
        s = get_settings()
        checks = {
            "smartstore": bool(s.naver_client_id and _valid_naver_commerce_secret(s.naver_client_secret)),
            "coupang": bool(s.coupang_access_key and s.coupang_secret_key and s.coupang_vendor_id),
            "ownerclan": bool(s.ownerclan_username and s.ownerclan_password),
            "domeggook": bool(s.domeggook_api_key),
            "domemai": bool(s.domemai_api_key),
            "onchannel": bool(s.onchannel_login_id and s.onchannel_login_pw),
            "ai": bool(s.claude_api_key or s.openai_api_key),
        }
        sales_ready = checks["smartstore"] or checks["coupang"]
        supplier_ready = any(checks[k] for k in ("ownerclan", "domeggook", "domemai", "onchannel"))
        return {
            "ready": bool(sales_ready and supplier_ready),
            "checks": checks,
            "sales_ready": sales_ready,
            "supplier_ready": supplier_ready,
        }
    except Exception as exc:
        return {"ready": False, "checks": {}, "error": str(exc)}


def get_process_status() -> dict[str, Any]:
    conn = _connection_state()
    counts: dict[str, int] = {}
    stage_done: dict[str, bool] = {s.key: False for s in WORKFLOW_STAGES}
    stage_done["connections"] = bool(conn.get("ready"))

    try:
        from app.db import (
            get_db, Product, Listing, PlatformOrder, Order,
            SettlementPeriod, SupplierRawProduct, SupplierWorkflowItem,
        )
        with get_db() as db:
            counts["products"] = _count(db, Product)
            counts["ready_products"] = _count(db, Product, status="ready")
            counts["listed_products"] = _count(db, Product, status="listed")
            counts["listings"] = _count(db, Listing, status="success")
            counts["platform_orders"] = _count(db, PlatformOrder)
            counts["shipped_orders"] = _count(db, PlatformOrder, status="shipped")
            counts["financial_orders"] = _count(db, Order)
            counts["settlements"] = _count(db, SettlementPeriod)
            counts["supplier_raw"] = _count(db, SupplierRawProduct)
            counts["workflow_items"] = _count(db, SupplierWorkflowItem)
            counts["selected_items"] = _count(db, SupplierRawProduct, is_selected=True)

            image_ready = 0
            detail_ready = 0
            for p in db.query(Product).all():
                try:
                    images = json.loads(p.images or "[]")
                    details = json.loads(p.detail_images or "[]")
                except Exception:
                    images, details = [], []
                if images:
                    image_ready += 1
                if details or (p.detail_html or "").strip():
                    detail_ready += 1
            counts["image_ready"] = image_ready
            counts["detail_ready"] = detail_ready
            counts["supplier_ordered"] = int(
                db.query(PlatformOrder).filter(PlatformOrder.supplier_order_id != "").count()
            )

        stage_done["acquire"] = bool(counts["supplier_raw"] > 0 or counts["products"] > 0 or counts["listings"] > 0)
        sale_candidates = counts["ready_products"] + counts["listed_products"]
        stage_done["prepare"] = bool(sale_candidates > 0 and counts["image_ready"] > 0)
        stage_done["listing"] = bool(counts["listings"] > 0 or counts["listed_products"] > 0)
        stage_done["orders"] = counts["platform_orders"] > 0
        stage_done["fulfillment"] = bool(counts["supplier_ordered"] > 0 or counts["shipped_orders"] > 0)
        stage_done["settlement"] = bool(counts["financial_orders"] > 0 or counts["settlements"] > 0)
    except Exception as exc:
        logger.warning("원큐 상태 DB 집계 실패: %s", exc)
        counts["db_error"] = 1

    required = [s for s in WORKFLOW_STAGES if not s.optional]
    completed_required = sum(1 for s in required if stage_done.get(s.key, False))
    progress = completed_required / len(required) if required else 0.0

    stages = []
    for stage in WORKFLOW_STAGES:
        row = stage.as_dict()
        row["done"] = bool(stage_done.get(stage.key, False))
        row["state"] = (
            "완료" if row["done"] else
            "승인 필요" if stage.approval_required else
            "선택" if stage.optional else
            "진행 필요"
        )
        stages.append(row)

    return {
        "progress": progress,
        "completed_required": completed_required,
        "required_total": len(required),
        "connections": conn,
        "counts": counts,
        "stages": stages,
    }


def get_next_stage(status: dict[str, Any] | None = None) -> dict[str, Any] | None:
    status = status or get_process_status()
    for row in status.get("stages", []):
        if not row.get("optional") and not row.get("done"):
            return row
    for row in status.get("stages", []):
        if not row.get("done"):
            return row
    return None


def _sync_marketplace_catalogs() -> dict[str, Any]:
    from app.sync.catalog_sync import sync_smartstore_catalog, sync_coupang_catalog
    return {
        "smartstore": sync_smartstore_catalog(),
        "coupang": sync_coupang_catalog(),
    }


def _refresh_supplier_images(limit: int = 100) -> dict[str, Any]:
    from app.db import get_db, Product
    from app.suppliers.registry import get_adapter
    from app.media.product_images import collect_product_images
    from app.media.marketplace_images import normalize_image_list

    updated = 0
    checked = 0
    errors: list[str] = []
    with get_db() as db:
        products = db.query(Product).order_by(Product.id.desc()).limit(max(1, int(limit))).all()
        for p in products:
            if p.source not in {"ownerclan", "domeggook", "domemai", "onchannel"} or not p.source_id:
                continue
            checked += 1
            try:
                adapter = get_adapter(p.source)
                fresh = adapter.get_product(p.source_id) if adapter else None
                if not fresh:
                    continue
                collected = collect_product_images(fresh, fetch_page=True)
                try:
                    old_images = json.loads(p.images or "[]")
                    old_details = json.loads(p.detail_images or "[]")
                except Exception:
                    old_images, old_details = [], []
                new_images = normalize_image_list([*old_images, *collected.images])
                new_details = normalize_image_list([*old_details, *collected.detail_images])
                if new_images != old_images or new_details != old_details:
                    p.images = json.dumps(new_images, ensure_ascii=False)
                    p.detail_images = json.dumps(new_details, ensure_ascii=False)
                    updated += 1
            except Exception as exc:
                errors.append(f"{p.sku}: {exc}")
        db.commit()
    return {"checked": checked, "updated": updated, "errors": errors[:10]}


def run_safe_oneclick(*, sync_marketplaces: bool = True, refresh_images: bool = True) -> dict[str, Any]:
    """비용/외부 등록을 만들지 않는 안전 작업만 실행한다.

    실행 순서:
    1) 판매채널 기존상품 읽기/동기화
    2) 공급처 원본 이미지 보완

    신규 판매상품 등록, 공급처 실제 주문, 유료 AI 이미지 생성은 포함하지 않는다.
    """
    results: dict[str, Any] = {"ok": True, "steps": []}

    if sync_marketplaces:
        try:
            value = _sync_marketplace_catalogs()
            # 한 판매채널 인증이 아직 안 되어 있어도 다른 채널 결과까지 폐기하지 않는다.
            ok_count = sum(1 for v in value.values() if bool(v.get("ok")))
            ok = ok_count > 0
            results["ok"] = results["ok"] and ok
            results["steps"].append({"key": "market_sync", "ok": ok, "result": value})
        except Exception as exc:
            results["ok"] = False
            results["steps"].append({"key": "market_sync", "ok": False, "error": str(exc)})

    if refresh_images:
        try:
            value = _refresh_supplier_images()
            results["steps"].append({"key": "images", "ok": True, "result": value})
        except Exception as exc:
            results["ok"] = False
            results["steps"].append({"key": "images", "ok": False, "error": str(exc)})

    results["status"] = get_process_status()
    results["next_stage"] = get_next_stage(results["status"])
    return results
