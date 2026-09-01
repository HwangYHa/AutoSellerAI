"""AI Campaign Director for the integrated product-growth workflow.

The director is a planning/orchestration layer, not a second publishing engine.  It
turns current product/workflow/performance facts into an ordered campaign plan and
can execute only the action tiers explicitly allowed by the caller.

Safety/cost boundaries:
- planning is local and side-effect free;
- tracking-link creation and reuse of existing product/detail visuals are local;
- Threads copy may call the configured AI provider, so it requires allow_ai_content;
- paid detail-image generation requires allow_paid_detail_generation;
- future Threads publishing is never hidden inside prepare_campaign(); scheduling
  has its own explicit function and still uses the existing ScheduledSocialPost path.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.db import get_db
from app.orchestration.campaign_director_models import CampaignDirectorPlan, ensure_campaign_director_schema
from app.orchestration.product_growth import (
    ensure_workflow_tracking,
    get_workflow,
    prepare_threads_drafts,
    queue_detail_generation,
    schedule_workflow_post,
    tracking_is_public,
    use_detail_social_visual,
    use_product_social_visual,
    workflow_to_dict,
)
from app.social.threads.profit_feedback import learning_context
from app.sqlite_runtime import retry_sqlite_write


_POSTING_WINDOWS_KST = ["12:20", "19:40", "22:10"]


def _loads(value: str, fallback):
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _public_urls(values: list[Any]) -> list[str]:
    return [str(x) for x in values if str(x).startswith(("http://", "https://"))]


def _fingerprint(state: dict[str, Any], learning: dict[str, Any]) -> str:
    product = state.get("product") or {}
    payload = {
        "workflow_id": state.get("id"),
        "campaign_key": state.get("campaign_key"),
        "target_platform": state.get("target_platform"),
        "destination_url": state.get("destination_url"),
        "threads_angle": state.get("threads_angle"),
        "threads_tone": state.get("threads_tone"),
        "product": {
            "id": product.get("id"),
            "name": product.get("name"),
            "category": product.get("category"),
            "brand": product.get("brand"),
            "material": product.get("material"),
            "sell_price": product.get("sell_price"),
            "image_count": len(product.get("images") or []),
            "detail_count": len(product.get("detail_images") or []),
            "detail_html": bool(product.get("detail_html")),
        },
        "workflow": {
            "draft_count": len(state.get("drafts") or []),
            "schedule_count": len(state.get("schedules") or []),
            "tracking_ready": bool((state.get("tracking") or {}).get("ready")),
            "social_visual": bool((state.get("social_visual") or {}).get("media_url")),
            "published_posts": (state.get("performance") or {}).get("published_posts", 0),
            "orders": (state.get("performance") or {}).get("attributed_orders", 0),
        },
        "learning": learning,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _recommended_angle(state: dict[str, Any], learning: dict[str, Any]) -> tuple[str, str]:
    preferred = [str(x) for x in learning.get("preferred_angles", []) if x]
    avoid = {str(x) for x in learning.get("avoid_angles", []) if x}
    if preferred and int(learning.get("sample_orders") or 0) >= 2:
        return preferred[0], "실제 주문·수익 피드백에서 우선순위가 높은 콘텐츠 각도"

    current = str(state.get("threads_angle") or "problem_solution")
    if current and current not in avoid:
        return current, "현재 캠페인 설정을 유지"

    category = str((state.get("product") or {}).get("category") or "").lower()
    if any(x in category for x in ("패션", "의류", "뷰티", "화장", "잡화")):
        return "experience", "패션·뷰티 계열은 사용 장면/취향 관찰형이 자연스러움"
    if any(x in category for x in ("주방", "생활", "가전", "전자", "자동차")):
        return "problem_solution", "기능·생활 불편을 연결하기 쉬운 카테고리"
    return "question", "실적 데이터가 적어 반응 탐색용 질문형으로 시작"


def _recommended_visual(state: dict[str, Any]) -> dict[str, Any]:
    product = state.get("product") or {}
    detail = _public_urls(product.get("detail_images") or [])
    main = _public_urls(product.get("images") or [])
    current = state.get("social_visual") or {}
    if current.get("media_url") and current.get("public"):
        return {"source": "workflow", "reason": "이미 검증된 공개 캠페인 이미지가 연결되어 있음"}
    if detail:
        return {"source": "detail", "reason": "상품 사실에 기반한 상세페이지 컷을 Threads에도 재사용"}
    if main:
        return {"source": "product", "reason": "정확한 상품 identity를 유지하기 위해 실제 대표 이미지를 우선"}
    return {
        "source": "stable_diffusion_lifestyle",
        "reason": "공개 상품 이미지가 없어 라이프스타일 보조 컷이 필요함. SD 이미지는 정확한 상품 identity 근거로 사용하지 않음",
    }


def _build_actions(state: dict[str, Any], visual: dict[str, Any]) -> list[dict[str, Any]]:
    product = state.get("product") or {}
    detail_ready = bool((state.get("detail") or {}).get("ready"))
    tracking = state.get("tracking") or {}
    drafts = state.get("drafts") or []
    actions: list[dict[str, Any]] = []

    actions.append({
        "id": "product_truth",
        "title": "상품 사실·원본 이미지 기준 고정",
        "tier": "local",
        "needed": True,
        "auto_allowed": True,
        "reason": f"{product.get('name') or '상품'}의 실제 이미지/확인된 정보가 모든 콘텐츠의 기준",
    })
    actions.append({
        "id": "detail_page",
        "title": "상세페이지 장면 준비",
        "tier": "ai_cost",
        "needed": not detail_ready,
        "auto_allowed": False,
        "reason": "기존 상세 자산이 없을 때만 reference 기반 생성 권장",
    })
    actions.append({
        "id": "tracking",
        "title": "Threads Tracking Link 준비",
        "tier": "local",
        "needed": bool(state.get("destination_url")) and not bool(tracking.get("ready")),
        "auto_allowed": True,
        "reason": "클릭→주문→수익 학습의 campaign_key 연결점",
    })
    actions.append({
        "id": "threads_copy",
        "title": "Threads 카피 변형 준비",
        "tier": "ai_compute",
        "needed": not bool(drafts),
        "auto_allowed": False,
        "reason": "AI 공급자가 설정되어 있으면 API 사용량이 발생할 수 있어 명시적 허용 필요",
    })
    actions.append({
        "id": "social_visual",
        "title": "Threads 소셜 비주얼 선택",
        "tier": "local",
        "needed": not bool((state.get("social_visual") or {}).get("media_url")),
        "auto_allowed": visual.get("source") in {"detail", "product", "workflow"},
        "reason": visual.get("reason", ""),
    })
    actions.append({
        "id": "schedule",
        "title": "Threads 예약 게시",
        "tier": "external_publish",
        "needed": not bool(state.get("schedules")),
        "auto_allowed": False,
        "reason": "예약 등록은 미래 외부 게시를 발생시키므로 별도 명시 실행",
    })
    return actions


def build_campaign_plan(workflow_id: int, *, force: bool = False) -> dict[str, Any]:
    """Build or reuse a zero-cost local campaign plan for one workflow."""
    ensure_campaign_director_schema()
    workflow = get_workflow(int(workflow_id))
    if not workflow:
        raise LookupError("workflow not found")
    state = workflow_to_dict(workflow)
    try:
        learning = learning_context(workflow.product_id) or {}
    except Exception:
        learning = {}
    fingerprint = _fingerprint(state, learning)

    with get_db() as db:
        existing = db.scalar(select(CampaignDirectorPlan).where(CampaignDirectorPlan.workflow_id == int(workflow_id)))
        if existing and existing.fingerprint == fingerprint and not force:
            data = plan_to_dict(existing)
            return {**data, "reused": True}

    angle, angle_reason = _recommended_angle(state, learning)
    visual = _recommended_visual(state)
    product = state.get("product") or {}
    detail_ready = bool((state.get("detail") or {}).get("ready"))
    has_destination = bool(state.get("destination_url"))
    tracking_public = bool((state.get("tracking") or {}).get("public"))

    warnings: list[str] = []
    if not has_destination:
        warnings.append("실제 상품 판매 URL이 없어 클릭→주문 Tracking을 완성할 수 없습니다.")
    elif not tracking_public:
        warnings.append("PUBLIC_BASE_URL이 공개 HTTPS 주소가 아니면 Threads 본문에 Tracking Link를 넣을 수 없습니다.")
    if not _public_urls(product.get("images") or []):
        warnings.append("공개 상품 대표 이미지가 없습니다. Stable Diffusion은 보조 라이프스타일 컷으로만 사용하세요.")

    plan = {
        "version": "campaign-director-1.0",
        "workflow_id": workflow.id,
        "product_id": workflow.product_id,
        "campaign_key": workflow.campaign_key,
        "objective": "상세페이지와 Threads 콘텐츠를 동일 campaign_key로 연결해 클릭·주문·수익 피드백까지 학습 가능한 판매 캠페인을 만든다.",
        "recommended": {
            "threads_angle": angle,
            "threads_angle_reason": angle_reason,
            "threads_tone": workflow.threads_tone,
            "draft_count": 3,
            "detail_scene_count": 0 if detail_ready else 3,
            "detail_scene_roles": [] if detail_ready else ["hero", "features", "usage"],
            "social_visual": visual,
            "posting_windows_kst": list(_POSTING_WINDOWS_KST),
            "posting_window_note": "고정 최적시간 보장이 아닌 운영용 초기 탐색 시간대이며 실제 수익 피드백으로 교체해야 합니다.",
        },
        "quality_gates": {
            "product_identity": "상세/판매 이미지의 상품 외형은 실제 상품 또는 reference 기반 자산을 우선",
            "stable_diffusion": "가상 인플루언서·분위기 보조 컷 전용; 정확한 상품 형태/로고의 근거로 사용 금지",
            "tracking": "공개 Tracking URL 확인 후 본문 삽입",
            "publishing": "Campaign Director prepare 단계에서는 게시하지 않음; scheduling은 별도 명시 호출",
            "learning": "주문 표본이 쌓이면 preferred_angles/순이익을 다음 계획에 반영",
        },
        "evidence": {
            "product_images": len(product.get("images") or []),
            "detail_images": len(product.get("detail_images") or []),
            "detail_ready": detail_ready,
            "existing_drafts": len(state.get("drafts") or []),
            "existing_schedules": len(state.get("schedules") or []),
            "published_posts": (state.get("performance") or {}).get("published_posts", 0),
            "attributed_orders": (state.get("performance") or {}).get("attributed_orders", 0),
            "learning": learning,
        },
        "actions": _build_actions(state, visual),
        "warnings": warnings,
    }

    def write() -> CampaignDirectorPlan:
        with get_db() as db:
            row = db.scalar(select(CampaignDirectorPlan).where(CampaignDirectorPlan.workflow_id == int(workflow_id)))
            if not row:
                row = CampaignDirectorPlan(workflow_id=int(workflow_id))
                db.add(row)
            row.fingerprint = fingerprint
            row.source = "rules+performance"
            row.status = "planned"
            row.plan_json = json.dumps(plan, ensure_ascii=False, default=str)
            row.error = ""
            db.commit()
            db.refresh(row)
            db.expunge(row)
            return row

    saved = retry_sqlite_write(write, attempts=6)
    return {**plan_to_dict(saved), "reused": False}


def get_campaign_plan(workflow_id: int) -> dict[str, Any] | None:
    ensure_campaign_director_schema()
    with get_db() as db:
        row = db.scalar(select(CampaignDirectorPlan).where(CampaignDirectorPlan.workflow_id == int(workflow_id)))
        if not row:
            return None
        db.expunge(row)
    return plan_to_dict(row)


def _record_execution(workflow_id: int, execution: dict[str, Any], status: str) -> None:
    ensure_campaign_director_schema()

    def write() -> None:
        with get_db() as db:
            row = db.scalar(select(CampaignDirectorPlan).where(CampaignDirectorPlan.workflow_id == int(workflow_id)))
            if not row:
                return
            previous = _loads(row.execution_json, {})
            history = list(previous.get("history") or [])
            history.append({**execution, "at": datetime.utcnow().isoformat()})
            row.execution_json = json.dumps({"last": execution, "history": history[-30:]}, ensure_ascii=False, default=str)
            row.status = status
            row.error = ""
            db.commit()

    retry_sqlite_write(write, attempts=6)


def prepare_campaign(
    workflow_id: int,
    *,
    allow_ai_content: bool = False,
    allow_paid_detail_generation: bool = False,
    draft_count: int = 3,
    force_drafts: bool = False,
) -> dict[str, Any]:
    """Execute explicitly allowed preparation tiers; never schedule/publish."""
    plan = build_campaign_plan(workflow_id)
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise LookupError("workflow not found")
    results: list[dict[str, Any]] = []

    if workflow.destination_url:
        try:
            link = ensure_workflow_tracking(workflow_id)
            results.append({"step": "tracking", "ok": True, "tracking_link_id": link.id, "public": tracking_is_public(link)})
        except Exception as exc:
            results.append({"step": "tracking", "ok": False, "error": str(exc)})

    state = workflow_to_dict(get_workflow(workflow_id))
    visual = ((plan.get("plan") or {}).get("recommended") or {}).get("social_visual") or {}
    if not (state.get("social_visual") or {}).get("media_url"):
        source = visual.get("source")
        try:
            if source == "detail":
                value = use_detail_social_visual(workflow_id, 0)
                results.append({"step": "social_visual", "ok": True, **value})
            elif source == "product":
                value = use_product_social_visual(workflow_id, 0)
                results.append({"step": "social_visual", "ok": True, **value})
            else:
                results.append({"step": "social_visual", "ok": True, "skipped": True, "reason": visual.get("reason", "manual visual needed")})
        except Exception as exc:
            results.append({"step": "social_visual", "ok": False, "error": str(exc)})

    if allow_ai_content:
        try:
            drafts = prepare_threads_drafts(workflow_id, count=max(1, min(int(draft_count), 5)), force=force_drafts)
            results.append({"step": "threads_copy", "ok": True, "draft_ids": [x.id for x in drafts], "count": len(drafts)})
        except Exception as exc:
            results.append({"step": "threads_copy", "ok": False, "error": str(exc)})
    else:
        results.append({"step": "threads_copy", "ok": True, "skipped": True, "reason": "allow_ai_content=false"})

    state = workflow_to_dict(get_workflow(workflow_id))
    if allow_paid_detail_generation and not (state.get("detail") or {}).get("ready"):
        try:
            detail_count = int((((plan.get("plan") or {}).get("recommended") or {}).get("detail_scene_count")) or 3)
            queued = queue_detail_generation(workflow_id, count=max(1, min(detail_count, 5)), apply=True)
            results.append({"step": "detail_generation", "ok": True, **queued})
        except Exception as exc:
            results.append({"step": "detail_generation", "ok": False, "error": str(exc)})
    elif not (state.get("detail") or {}).get("ready"):
        results.append({"step": "detail_generation", "ok": True, "skipped": True, "reason": "allow_paid_detail_generation=false"})

    ok = all(bool(x.get("ok")) for x in results)
    status = "prepared" if ok else "partial_failed"
    execution = {
        "type": "prepare",
        "ok": ok,
        "allow_ai_content": allow_ai_content,
        "allow_paid_detail_generation": allow_paid_detail_generation,
        "results": results,
    }
    _record_execution(workflow_id, execution, status)
    return {**execution, "workflow": workflow_to_dict(get_workflow(workflow_id))}


def schedule_director_post(
    workflow_id: int,
    *,
    scheduled_at: datetime,
    draft_id: int | None = None,
    media_source: str = "auto",
    include_tracking_url: bool = True,
) -> dict[str, Any]:
    """Explicit future-publish action. No copy/image generation is hidden here."""
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise LookupError("workflow not found")
    state = workflow_to_dict(workflow)
    drafts = list(state.get("drafts") or [])
    if not drafts:
        raise ValueError("Threads drafts are not prepared; explicitly run AI content preparation first")

    if draft_id is None:
        chosen = max(drafts, key=lambda x: float(x.get("score") or 0))
        draft_id = int(chosen["id"])
    elif int(draft_id) not in {int(x["id"]) for x in drafts}:
        raise ValueError("draft_id does not belong to this campaign")

    source = str(media_source or "auto").lower()
    if source == "auto":
        if (state.get("social_visual") or {}).get("media_url"):
            source = "workflow"
        elif _public_urls((state.get("product") or {}).get("detail_images") or []):
            source = "detail"
        elif _public_urls((state.get("product") or {}).get("images") or []):
            source = "product"
        else:
            source = "none"

    scheduled = schedule_workflow_post(
        workflow_id,
        draft_id=int(draft_id),
        scheduled_at=scheduled_at,
        media_source=source,
        include_tracking_url=include_tracking_url,
    )
    execution = {
        "type": "schedule",
        "ok": True,
        "schedule_id": scheduled.id,
        "draft_id": int(draft_id),
        "media_source": source,
        "scheduled_at": scheduled.scheduled_at.isoformat(),
    }
    _record_execution(workflow_id, execution, "scheduled")
    return execution


def plan_to_dict(row: CampaignDirectorPlan) -> dict[str, Any]:
    return {
        "id": row.id,
        "workflow_id": row.workflow_id,
        "fingerprint": row.fingerprint,
        "source": row.source,
        "status": row.status,
        "plan": _loads(row.plan_json, {}),
        "execution": _loads(row.execution_json, {}),
        "error": row.error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


__all__ = [
    "build_campaign_plan",
    "get_campaign_plan",
    "prepare_campaign",
    "schedule_director_post",
    "plan_to_dict",
]
