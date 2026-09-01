"""Unified product detail-page -> Threads growth campaign workspace."""
from __future__ import annotations

import json
from datetime import datetime, time
from zoneinfo import ZoneInfo

import streamlit as st

from app.db import Product, get_db
from app.image_studio.service import list_generations
from app.orchestration.product_growth import (
    attach_image_generation,
    create_workflow,
    get_workflow,
    list_workflows,
    prepare_threads_drafts,
    queue_detail_generation,
    schedule_workflow_post,
    stage_attached_social_visual,
    use_product_social_visual,
    workflow_to_dict,
)
from app.social.threads.media import media_base_is_public
from app.social.threads.zalpa_content import ANGLES, TONE_LABELS


st.set_page_config(page_title="상품 성장 워크플로우 | AutoSellerAI", page_icon="🚀", layout="wide")
st.title("🚀 상품 상세페이지 · Threads 통합 워크플로우")
st.caption("상품 하나를 기준으로 상세페이지 자산 → Threads 초안 → 소셜 이미지 → 추적 링크 → 예약 게시 → 주문귀속을 하나의 campaign_key로 연결합니다.")

with get_db() as db:
    products = db.query(Product).order_by(Product.id.desc()).limit(1000).all()
    product_rows = [
        {
            "id": p.id,
            "name": p.name,
            "source": p.source,
            "status": p.status,
            "images": json.loads(p.images or "[]"),
            "detail_images": json.loads(p.detail_images or "[]"),
            "detail_html": p.detail_html or "",
        }
        for p in products
    ]

if not product_rows:
    st.info("먼저 상품을 수집하거나 판매채널 상품을 동기화하세요.")
    st.stop()

selected_product = st.selectbox(
    "상품 선택",
    product_rows,
    format_func=lambda x: f"#{x['id']} · {x['name']} · {x['source']}",
)

with st.expander("➕ 새 캠페인 만들기", expanded=not bool(list_workflows(limit=1, product_id=selected_product["id"]))):
    c1, c2 = st.columns(2)
    target_platform = c1.selectbox("판매 연결 채널", ["smartstore", "coupang"], format_func=lambda x: "네이버 스마트스토어" if x == "smartstore" else "쿠팡")
    destination_url = c2.text_input("실제 상품 판매 URL", placeholder="https://...")
    c3, c4 = st.columns(2)
    angle = c3.selectbox("Threads 콘텐츠 각도", list(ANGLES.keys()), format_func=lambda x: ANGLES[x])
    tone = c4.selectbox("Threads 말투", list(TONE_LABELS.keys()), format_func=lambda x: TONE_LABELS[x])
    cta_keyword = st.text_input("댓글 CTA 키워드", placeholder="비우면 상품 정보에서 자동 생성")
    if st.button("🚀 통합 캠페인 생성", type="primary", use_container_width=True):
        try:
            row = create_workflow(
                selected_product["id"],
                target_platform=target_platform,
                destination_url=destination_url,
                cta_keyword=cta_keyword,
                threads_angle=angle,
                threads_tone=tone,
            )
            st.session_state["product_growth_workflow_id"] = row.id
            st.success(f"캠페인 #{row.id} 생성 완료 · {row.campaign_key}")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

workflows = list_workflows(limit=100, product_id=selected_product["id"])
if not workflows:
    st.info("이 상품의 통합 캠페인을 먼저 생성하세요.")
    st.stop()

preferred_id = st.session_state.get("product_growth_workflow_id")
index = next((i for i, row in enumerate(workflows) if row.id == preferred_id), 0)
workflow = st.selectbox(
    "캠페인 선택",
    workflows,
    index=index,
    format_func=lambda x: f"#{x.id} · {x.campaign_key}",
)
st.session_state["product_growth_workflow_id"] = workflow.id
state = workflow_to_dict(get_workflow(workflow.id))

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("상태", state["status"])
m2.metric("상세페이지", "준비" if state["detail"]["ready"] else "미준비")
m3.metric("Threads 초안", len(state["drafts"]))
m4.metric("예약/게시", len(state["schedules"]))
m5.metric("귀속 주문", state["performance"]["attributed_orders"])
st.code(state["campaign_key"], language=None)

st.markdown("### 연결 흐름")
st.markdown("**상품 사실/원본 → 상세페이지 → Threads 초안 → 소셜 비주얼 → Tracking Link → 예약 게시 → 클릭·주문귀속·수익학습**")

with st.expander("현재 캠페인 상태 자세히", expanded=False):
    st.json(state)

st.divider()
left, right = st.columns(2)
with left:
    st.markdown("### 1. 상세페이지 자산")
    detail = state["detail"]
    st.write(f"현재 상품 상세 이미지 **{len(state['product']['detail_images']) if state.get('product') else 0}장**")
    if detail["ready"]:
        st.success("상품 상세페이지 자산이 준비되어 있습니다.")
    else:
        st.warning("상세페이지 이미지 또는 HTML이 아직 없습니다.")

    references = (state.get("product") or {}).get("images") or []
    reference_url = st.selectbox("상품 외형 기준 이미지", [""] + references, format_func=lambda x: "선택 안 함" if not x else x)
    detail_count = st.slider("새 상세페이지 장면 수", 1, 5, 3)
    paid_confirm = st.checkbox("유료 AI 상세 이미지 생성을 명시적으로 실행합니다.")
    if st.button("🖼️ 상세페이지 AI 생성 큐 등록", use_container_width=True, disabled=not paid_confirm):
        try:
            result = queue_detail_generation(workflow.id, count=detail_count, reference_url=reference_url, apply=True)
            st.success(f"image-worker에 등록했습니다. Job: {result['job_id']}")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

with right:
    st.markdown("### 2. Threads 카피")
    if not state["destination_url"]:
        st.warning("판매 URL이 없어 Tracking Link를 만들 수 없습니다. 카피 초안은 만들 수 있지만 주문귀속 연결은 불완전합니다.")
    draft_count = st.slider("생성 초안 수", 1, 5, 3, key="growth_draft_count")
    force_drafts = st.checkbox("기존 초안을 재사용하지 않고 새 변형 생성", value=False)
    if st.button("✍️ Threads 초안 준비", use_container_width=True):
        try:
            drafts = prepare_threads_drafts(workflow.id, count=draft_count, force=force_drafts)
            st.success(f"Threads 초안 {len(drafts)}개 준비 완료")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    for draft in state["drafts"]:
        with st.container(border=True):
            st.caption(f"Draft #{draft['id']} · score {float(draft['score'] or 0):.1f} · {draft['status']}")
            st.write(draft["body"])

st.divider()
st.markdown("### 3. Threads 이미지 연결")
vis1, vis2 = st.columns(2)
with vis1:
    st.markdown("#### 실제 상품 이미지 사용")
    product_images = (state.get("product") or {}).get("images") or []
    if product_images:
        image_idx = st.selectbox("상품 이미지 번호", list(range(len(product_images))), format_func=lambda i: f"#{i + 1} · {product_images[i]}")
        st.image(product_images[image_idx], width=360)
        if st.button("✅ 이 상품 이미지를 Threads 캠페인에 연결", use_container_width=True):
            try:
                use_product_social_visual(workflow.id, image_idx)
                st.success("상품 이미지를 소셜 비주얼로 연결했습니다.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    else:
        st.info("공개 URL 상품 이미지가 없습니다.")

with vis2:
    st.markdown("#### Stable Diffusion 라이프스타일 이미지 사용")
    st.caption("Stable Diffusion txt2img는 정확한 상품 복제용이 아닙니다. 가상 인플루언서·분위기·라이프스타일 소셜 컷에만 사용하세요.")
    completed = [row for row in list_generations(limit=100) if str(row.status) == "completed"]
    if completed:
        generation = st.selectbox("완료된 AI 인물 이미지", completed, format_func=lambda x: f"Generation #{x.id} · {x.preset or '-'} · {x.subject_summary[:50]}")
        if st.button("🔗 이 Generation 연결", use_container_width=True):
            try:
                attach_image_generation(workflow.id, generation.id)
                st.success(f"Generation #{generation.id} 연결 완료")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if state["social_visual"]["image_generation_id"]:
            if st.button("📤 Threads 공개 미디어로 스테이징", use_container_width=True):
                try:
                    result = stage_attached_social_visual(workflow.id, 0)
                    if result["public"]:
                        st.success("Threads가 접근 가능한 공개 이미지 URL로 준비했습니다.")
                    else:
                        st.warning("파일은 준비됐지만 PUBLIC_BASE_URL/THREADS_MEDIA_PUBLIC_BASE_URL이 외부 공개 주소가 아닙니다.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    else:
        st.info("완료된 Stable Diffusion Generation이 없습니다. AI 인물 이미지 스튜디오에서 먼저 생성하세요.")

if state["social_visual"]["media_url"]:
    st.info(f"현재 Threads 이미지: {state['social_visual']['media_url']}")
if not media_base_is_public():
    st.warning("Threads 로컬 미디어를 Meta가 가져가려면 PUBLIC_BASE_URL 또는 THREADS_MEDIA_PUBLIC_BASE_URL을 인터넷에서 접근 가능한 HTTPS 주소로 설정해야 합니다.")

st.divider()
st.markdown("### 4. 예약 게시 · Tracking")
if state["tracking"]["ready"]:
    st.success(f"Tracking Link 준비: {state['tracking']['url']}")
elif state["destination_url"]:
    st.info("Threads 초안을 준비하면 Tracking Link가 자동 생성됩니다.")
else:
    st.warning("실제 판매 URL이 없어 클릭→주문 귀속 링크를 만들 수 없습니다.")

if state["drafts"]:
    draft_choice = st.selectbox("게시할 초안", state["drafts"], format_func=lambda x: f"Draft #{x['id']} · {x['body'][:55]}")
    s1, s2 = st.columns(2)
    schedule_date = s1.date_input("게시 날짜")
    schedule_time = s2.time_input("게시 시간", value=time(19, 0))
    media_source = st.radio(
        "게시 이미지",
        ["workflow", "product", "none"],
        horizontal=True,
        format_func=lambda x: {"workflow": "현재 캠페인 이미지", "product": "상품 대표이미지", "none": "텍스트만"}[x],
    )
    include_tracking = st.checkbox("게시문에 Tracking Link 포함", value=True)
    if st.button("🗓️ Threads 예약 게시 등록", type="primary", use_container_width=True):
        try:
            local_dt = datetime.combine(schedule_date, schedule_time).replace(tzinfo=ZoneInfo("Asia/Seoul"))
            utc_dt = local_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            scheduled = schedule_workflow_post(
                workflow.id,
                draft_id=draft_choice["id"],
                scheduled_at=utc_dt,
                media_source=media_source,
                include_tracking_url=include_tracking,
            )
            st.success(f"예약 #{scheduled.id} 등록 완료 · {local_dt.strftime('%Y-%m-%d %H:%M')} KST")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
else:
    st.info("먼저 Threads 초안을 준비하세요.")

st.divider()
st.markdown("### 5. 성과 연결")
p1, p2, p3 = st.columns(3)
p1.metric("게시 완료", state["performance"]["published_posts"])
p2.metric("귀속 주문", state["performance"]["attributed_orders"])
p3.metric("귀속 매출", f"{state['performance']['attributed_revenue']:,.0f}원")
st.caption("게시 후 기존 Threads 스케줄러가 클릭 추적 → 주문 귀속 → 수익 피드백을 수행합니다. 다음 콘텐츠 생성 시 누적 성과가 다시 콘텐츠 각도 선택에 반영됩니다.")
