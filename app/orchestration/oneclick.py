"""AutoSellerAI 원큐 운영 플로우.

전체 업무를 한 화면에서 순서대로 진행하기 위한 오케스트레이터다.
조회/동기화처럼 되돌릴 수 있는 작업은 '안전 자동실행'에 포함하고,
실제 상품등록·공급처 발주처럼 외부 상태/비용을 바꾸는 작업은 명시적 승인 단계로 남긴다.
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
    WorkflowStage(1, "connections", "초기 설정 · API 연동", "판매채널·공급처·AI 인증과 연결 상태를 확인합니다.", "pages/20_오너클랜_연동.py"),
    WorkflowStage(2, "market_sync", "기존 판매상품 동기화", "쿠팡·스마트스토어 판매자센터에 이미 있는 상품을 내부 DB와 맞춥니다.", "pages/05_판매채널_상품동기화.py", safe_auto=True),
    WorkflowStage(3, "collect", "공급처 상품 수집", "오너클랜·도매꾹·도매매·온채널에서 판매 후보를 수집합니다.", "pages/00_AutoSeller_Main.py"),
    WorkflowStage(4, "select", "AI 상품 선별", "마진·수요·경쟁·공급 안정성을 기준으로 판매 후보를 선별합니다.", "pages/00_AutoSeller_Main.py"),
    WorkflowStage(5, "images", "상품 이미지 · 상세정보 수집", "공급처 API와 상품 HTML의 이미지 태그에서 대표/상세 이미지를 복원합니다.", "pages/25_AI_상세페이지_제작.py", safe_auto=True),
    WorkflowStage(6, "ai_detail", "AI 상세페이지 보강", "원본 상세 이미지가 부족할 때만 reference 기반 AI 이미지를 선택적으로 제작합니다.", "pages/25_AI_상세페이지_제작.py", optional=True),
    WorkflowStage(7, "seo", "SEO · GEO · AEO 최적화", "상품명·키워드·FAQ·상세정보를 검색엔진과 AI 답변엔진에 맞게 정리합니다.", "pages/00_AutoSeller_Main.py"),
    WorkflowStage(8, "pricing", "판매가 · 순이익 검증", "공급가·배송비·플랫폼 수수료·광고비를 반영해 손실 상품을 차단합니다.", "pages/00_AutoSeller_Main.py"),
    WorkflowStage(9, "listing", "쿠팡 · 스마트스토어 등록", "검수된 상품을 판매채널에 실제 등록합니다.", "pages/00_AutoSeller_Main.py", approval_required=True),
    WorkflowStage(10, "orders", "주문 수집", "쿠팡·스마트스토어 신규 주문을 통합 수집합니다.", "pages/00_AutoSeller_Main.py", safe_auto=True),
    WorkflowStage(11, "fulfillment", "공급처 발주", "주문 상품·옵션·수취정보를 검증한 뒤 공급처에 발주합니다.", "pages/00_AutoSeller_Main.py", approval_required=True),
    WorkflowStage(12, "invoice", "송장 · 배송 동기화", "공급처의 실제 택배사/송장을 회수해 판매채널에 배송 처리합니다.", "pages/00_AutoSeller_Main.py", safe_auto=True),
    WorkflowStage(13, "settlement", "정산 · 실제 순이익", "매출·공급가·수수료·배송·광고·반품·세금을 합쳐 실제 순이익을 계산합니다.", "pages/00_AutoSeller_Main.py"),
    WorkflowStage(14, "threads", "스레드 판매 콘텐츠", "등록 상품으로 SEO·GEO·AEO 기반 스레드 콘텐츠와 추적 링크를 운영합니다.", "pages/10_Social_Commerce_Threads.py", optional=True),
    WorkflowStage(15, "learning", "구매 귀속 · 수익 학습", "클릭→마켓 주문→정산 순이익을 콘텐츠 점수와 다음 판매전략에 되먹임합니다.", "pages/12_Threads_Profit_Intelligence.py", optional=True, safe_auto=True),
)


def _count(db, model, **filters) -> int:
    q = db.query(model)
    if filters:
        q = q.filter_by(**filters)
    return int(q.count())


def _connection_state() -> dict[str, Any]:
    try:
        from app.config import get_settings
        s = get_settings()
        checks = {
            "smartstore": bool(s.naver_client_id and s.naver_client_secret),
            "coupang": bool(s.coupang_access_key and s.coupang_secret_key and s.coupang_vendor_id),
            "ownerclan": bool(s.ownerclan_username and s.ownerclan_password),
            "ai": bool(s.claude_api_key or s.openai_api_key),
        }
        return {"ready": bool(checks["smartstore"] and checks["coupang"]), "checks": checks}
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

            supplier_ordered = db.query(PlatformOrder).filter(PlatformOrder.supplier_order_id != "").count()

        stage_done["market_sync"] = counts["products"] > 0 or counts["listings"] > 0
        stage_done["collect"] = counts["supplier_raw"] > 0 or counts["products"] > 0
        stage_done["select"] = counts["selected_items"] > 0 or counts["ready_products"] > 0 or counts["listed_products"] > 0
        stage_done["images"] = counts["image_ready"] > 0
        stage_done["ai_detail"] = counts["detail_ready"] > 0
        stage_done["seo"] = counts["ready_products"] > 0 or counts["listed_products"] > 0
        stage_done["pricing"] = counts["ready_products"] > 0 or counts["listed_products"] > 0
        stage_done["listing"] = counts["listings"] > 0 or counts["listed_products"] > 0
        stage_done["orders"] = counts["platform_orders"] > 0
        stage_done["fulfillment"] = supplier_ordered > 0
        stage_done["invoice"] = counts["shipped_orders"] > 0
        stage_done["settlement"] = counts["financial_orders"] > 0 or counts["settlements"] > 0
    except Exception as exc:
        logger.warning("원큐 상태 DB 집계 실패: %s", exc)
        counts["db_error"] = 1

    counts.setdefault("threads_posts", 0)
    counts.setdefault("profit_snapshots", 0)

    required = [s for s in WORKFLOW_STAGES if not s.optional]
    completed_required = sum(1 for s in required if stage_done.get(s.key, False))
    progress = completed_required / len(required) if required else 0.0

    stages = []
    for s in WORKFLOW_STAGES:
        row = s.as_dict()
        row["done"] = bool(stage_done.get(s.key, False))
        row["state"] = (
            "완료" if row["done"] else
            "승인 필요" if s.approval_required else
            "선택" if s.optional else
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
                old_images = json.loads(p.images or "[]")
                old_details = json.loads(p.detail_images or "[]")
                new_images = list(dict.fromkeys([*old_images, *collected.images]))
                new_details = list(dict.fromkeys([*old_details, *collected.detail_images]))
                if new_images != old_images or new_details != old_details:
                    p.images = json.dumps(new_images, ensure_ascii=False)
                    p.detail_images = json.dumps(new_details, ensure_ascii=False)
                    updated += 1
            except Exception as exc:
                errors.append(f"{p.sku}: {exc}")
        db.commit()
    return {"checked": checked, "updated": updated, "errors": errors[:10]}


def run_safe_oneclick(*, sync_marketplaces: bool = True, refresh_images: bool = True) -> dict[str, Any]:
    """비용/외부 등록을 만들지 않는 안전 단계만 순서대로 실행한다.

    신규 판매상품 등록, 공급처 실제 주문, 유료 AI 이미지 생성은 의도적으로 포함하지 않는다.
    """
    results: dict[str, Any] = {"ok": True, "steps": []}

    if sync_marketplaces:
        try:
            value = _sync_marketplace_catalogs()
            ok = all(bool(v.get("ok")) for v in value.values())
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
