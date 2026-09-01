"""AI Campaign Director workspace for product-growth campaigns."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import streamlit as st

from app.orchestration.campaign_director import (
    build_campaign_plan,
    get_campaign_plan,
    prepare_campaign,
    schedule_director_post,
)
from app.orchestration.product_growth import list_workflows, workflow_to_dict
from gui.korean_runtime import apply_korean_patch


apply_korean_patch()
st.set_page_config(page_title="AI Campaign Director | AutoSellerAI", page_icon="🧠", layout="wide")
st.title("🧠 AI Campaign Director")
st.caption("상품 상세페이지 · Threads 카피 · 소셜 비주얼 · Tracking · 예약 게시를 하나의 campaign_key 기준으로 자동 기획합니다.")

workflows = list_workflows(limit=200)
if not workflows:
    st.info("먼저 ‘상품 성장 워크플로우’에서 캠페인을 생성하세요.")
    st.stop()

workflow = st.selectbox(
    "캠페인 선택",
    workflows,
    format_func=lambda x: f"#{x.id} · 상품 #{x.product_id} · {x.campaign_key}",
)
state = workflow_to_dict(workflow)
product = state.get("product") or {}

m1, m2, m3, m4 = st.columns(4)
m1.metric("상품", product.get("name") or f"#{workflow.product_id}")
m2.metric("상세페이지", "준비" if (state.get("detail") or {}).get("ready") else "미준비")
m3.metric("Threads 초안", len(state.get("drafts") or []))
m4.metric("귀속 주문", int((state.get("performance") or {}).get("attributed_orders") or 0))
st.code(state.get("campaign_key") or "", language=None)

st.markdown("### 1. 캠페인 자동 기획")
p1, p2 = st.columns([3, 1])
with p1:
    st.caption("현재 상품 자산·Threads 상태·Tracking·주문/수익 피드백을 읽고 다음 실행 순서를 계산합니다. 이 단계는 외부 게시나 유료 이미지 생성을 하지 않습니다.")
with p2:
    force = st.checkbox("강제 재계산", value=False)

if st.button("🧠 Campaign Plan 생성", type="primary", use_container_width=True):
    try:
        result = build_campaign_plan(workflow.id, force=force)
        st.success("캠페인 계획을 생성했습니다." + (" 기존 계획 재사용" if result.get("reused") else ""))
        st.rerun()
    except Exception as exc:
        st.error(str(exc))

plan_row = get_campaign_plan(workflow.id)
if not plan_row:
    st.info("Campaign Plan을 먼저 생성하세요.")
    st.stop()

plan = plan_row.get("plan") or {}
recommended = plan.get("recommended") or {}
visual = recommended.get("social_visual") or {}

r1, r2, r3, r4 = st.columns(4)
r1.metric("추천 Threads 각도", recommended.get("threads_angle") or "-")
r2.metric("초안 수", int(recommended.get("draft_count") or 0))
r3.metric("새 상세 장면", int(recommended.get("detail_scene_count") or 0))
r4.metric("추천 비주얼", visual.get("source") or "-")

st.info(str(recommended.get("threads_angle_reason") or ""))
st.caption(f"비주얼 전략: {visual.get('reason') or '-'}")

if plan.get("warnings"):
    st.warning("\n".join(f"• {x}" for x in plan["warnings"]))

st.markdown("#### 실행 순서")
for action in plan.get("actions") or []:
    icon = {"local": "✅", "ai_compute": "🤖", "ai_cost": "💳", "external_publish": "📤"}.get(action.get("tier"), "•")
    needed = "필요" if action.get("needed") else "이미 충족"
    st.write(f"{icon} **{action.get('title')}** · {needed} · `{action.get('tier')}`")
    st.caption(action.get("reason") or "")

with st.expander("기획 근거 / 품질 게이트"):
    st.json({"evidence": plan.get("evidence"), "quality_gates": plan.get("quality_gates")})

st.divider()
st.markdown("### 2. 허용한 범위만 준비 실행")
st.caption("아래 두 체크는 비용 가능성이 있는 작업입니다. 체크하지 않으면 Tracking과 기존 상품/상세 이미지 재사용 같은 로컬 작업만 수행합니다.")
allow_ai = st.checkbox("🤖 Threads AI 카피 생성 허용", value=False)
allow_paid_detail = st.checkbox("💳 유료 상세페이지 AI 이미지 생성 허용", value=False)
draft_count = st.slider("Threads 초안 수", 1, 5, int(recommended.get("draft_count") or 3))
force_drafts = st.checkbox("기존 Threads 초안 대신 새 변형 생성", value=False)

if st.button("⚙️ 허용 범위 준비 실행", use_container_width=True):
    try:
        result = prepare_campaign(
            workflow.id,
            allow_ai_content=allow_ai,
            allow_paid_detail_generation=allow_paid_detail,
            draft_count=draft_count,
            force_drafts=force_drafts,
        )
        if result.get("ok"):
            st.success("Campaign Director 준비 작업이 완료되었습니다.")
        else:
            st.warning("일부 단계가 실패했습니다. 결과를 확인하세요.")
        st.json(result.get("results") or [])
        st.rerun()
    except Exception as exc:
        st.error(str(exc))

execution = (get_campaign_plan(workflow.id) or {}).get("execution") or {}
if execution.get("last"):
    with st.expander("최근 Director 실행 결과"):
        st.json(execution["last"])

st.divider()
st.markdown("### 3. 예약 게시 — 명시 실행")
state = workflow_to_dict(workflow)
drafts = state.get("drafts") or []
if not drafts:
    st.info("예약하려면 먼저 Threads 초안을 명시적으로 생성하세요.")
else:
    best = max(drafts, key=lambda x: float(x.get("score") or 0))
    draft = st.selectbox(
        "게시 초안",
        drafts,
        index=next((i for i, x in enumerate(drafts) if x.get("id") == best.get("id")), 0),
        format_func=lambda x: f"#{x['id']} · score {float(x.get('score') or 0):.1f} · {str(x.get('body') or '')[:65]}",
    )
    s1, s2 = st.columns(2)
    post_date = s1.date_input("게시 날짜")
    post_time = s2.time_input("게시 시간", value=time(19, 40))
    media_source = st.selectbox(
        "게시 이미지",
        ["auto", "workflow", "detail", "product", "none"],
        format_func=lambda x: {
            "auto": "Director 자동 선택",
            "workflow": "현재 캠페인 이미지",
            "detail": "상세페이지 이미지",
            "product": "상품 대표 이미지",
            "none": "텍스트만",
        }[x],
    )
    include_tracking = st.checkbox("공개 Tracking Link 포함", value=True)
    confirm_schedule = st.checkbox("이 작업은 지정 시각에 실제 Threads 게시로 이어지는 예약임을 확인합니다.")

    if st.button("🗓️ Director 예약 게시 등록", type="primary", use_container_width=True, disabled=not confirm_schedule):
        try:
            local_dt = datetime.combine(post_date, post_time).replace(tzinfo=ZoneInfo("Asia/Seoul"))
            utc_dt = local_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            result = schedule_director_post(
                workflow.id,
                scheduled_at=utc_dt,
                draft_id=int(draft["id"]),
                media_source=media_source,
                include_tracking_url=include_tracking,
            )
            st.success(f"예약 #{result['schedule_id']} 등록 · {local_dt:%Y-%m-%d %H:%M} KST")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

st.divider()
st.markdown("### 4. 현재 성과")
state = workflow_to_dict(workflow)
perf = state.get("performance") or {}
c1, c2, c3 = st.columns(3)
c1.metric("게시 완료", int(perf.get("published_posts") or 0))
c2.metric("귀속 주문", int(perf.get("attributed_orders") or 0))
c3.metric("귀속 매출", f"{float(perf.get('attributed_revenue') or 0):,.0f}원")
st.caption("주문/수익 표본이 쌓이면 다음 Campaign Plan에서 preferred_angles와 수익 피드백을 자동 반영합니다.")
