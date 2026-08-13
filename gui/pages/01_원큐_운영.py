"""AutoSellerAI 전체 프로세스를 순서대로 진행하는 원큐 운영 화면."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st

from app.orchestration.oneclick import get_process_status, get_next_stage, run_safe_oneclick
from gui.korean_runtime import apply_korean_patch
from app.policies.runtime_patch import apply_fulfillment_policy_patch

apply_korean_patch()
apply_fulfillment_policy_patch()

st.set_page_config(page_title="원큐 운영 | 오토셀러 AI", page_icon="🚀", layout="wide")

st.markdown("# 🚀 원큐 운영")
st.caption("초기 연동 → 상품 → 등록 → 주문 → 발주 → 배송 → 정산 → 광고 → 수익 학습을 한 화면에서 순서대로 진행합니다.")
st.info("조회·동기화처럼 안전한 작업은 한 번에 실행합니다. 실제 상품등록, 공급처 발주, 유료 AI 이미지 생성은 비용·외부 상태를 바꾸므로 해당 단계에서 명시적으로 승인해야 합니다.")

status = get_process_status()

st.markdown("### ⚡ 한큐 안전 실행")
left, right = st.columns([2, 1])
with left:
    st.write("쿠팡·스마트스토어 기존상품 역동기화 → 공급처 원본 이미지/상세이미지 재수집 순서로 실행합니다. 신규 상품등록·실제 공급처 발주·유료 AI 생성은 포함하지 않습니다.")
with right:
    run_clicked = st.button("▶ 안전 단계 한큐 실행", type="primary", use_container_width=True)

if run_clicked:
    with st.spinner("판매채널 동기화 → 이미지 보완을 순서대로 실행 중입니다..."):
        result = run_safe_oneclick()
    st.session_state["oneclick_last_result"] = result
    status = result.get("status") or get_process_status()

last_result = st.session_state.get("oneclick_last_result")
if last_result:
    if last_result.get("ok"):
        st.success("안전 자동화 단계를 완료했습니다.")
    else:
        st.warning("일부 단계에서 오류가 발생했습니다. 결과를 확인하고 해당 단계에서 복구하세요.")
    for step in last_result.get("steps", []):
        label = "✅" if step.get("ok") else "❌"
        with st.expander(f"{label} {step.get('key')}", expanded=not step.get("ok")):
            st.json(step.get("result") if step.get("ok") else {"error": step.get("error")})

progress = float(status.get("progress", 0.0))
st.progress(progress, text=f"필수 단계 진행도 {status.get('completed_required', 0)}/{status.get('required_total', 0)} · {progress*100:.0f}%")

counts = status.get("counts", {})
a, b, c, d = st.columns(4)
a.metric("내부 상품", counts.get("products", 0))
b.metric("판매채널 등록", counts.get("listings", 0))
c.metric("수집 주문", counts.get("platform_orders", 0))
d.metric("정산 주문", counts.get("financial_orders", 0))

st.markdown("### 🧭 전체 판매 프로세스")
for row in status.get("stages", []):
    if row.get("done"):
        badge = "✅ 완료"
    elif row.get("approval_required"):
        badge = "🟠 승인 필요"
    elif row.get("optional"):
        badge = "⚪ 선택"
    else:
        badge = "🔵 진행 필요"

    with st.container(border=True):
        cols = st.columns([0.8, 5.2, 1.5])
        with cols[0]:
            st.markdown(f"### {row['order']:02d}")
        with cols[1]:
            st.markdown(f"**{row['title']}** · {badge}")
            st.caption(row["description"])
            flags = []
            if row.get("safe_auto"):
                flags.append("안전 자동화 가능")
            if row.get("approval_required"):
                flags.append("실행 전 사용자 승인")
            if row.get("optional"):
                flags.append("선택 단계")
            if flags:
                st.caption(" · ".join(flags))
        with cols[2]:
            st.page_link(row["page"], label="이 단계 열기", icon="➡️", use_container_width=True)

next_stage = get_next_stage(status)
st.markdown("### 🎯 지금 해야 할 다음 단계")
if next_stage:
    with st.container(border=True):
        st.markdown(f"**{next_stage['order']:02d}. {next_stage['title']}**")
        st.write(next_stage["description"])
        if next_stage.get("approval_required"):
            st.warning("이 단계는 판매채널 등록 또는 실제 발주처럼 외부 상태/비용을 변경합니다. 해당 화면에서 내용을 검수하고 승인 후 실행하세요.")
        st.page_link(next_stage["page"], label="다음 단계로 이동", icon="🚀", use_container_width=True)
else:
    st.success("필수 프로세스가 모두 진행된 상태입니다. 선택 단계와 수익 인텔리전스를 점검하세요.")

st.markdown("### 🔁 표준 운영 원칙")
st.write("신규 상품은 01→15 순서로 진행합니다. 운영 중에는 판매채널 상품·주문·공급처 재고·송장·정산·수익학습을 반복 동기화합니다. 실패한 단계가 있으면 이후 단계를 억지로 실행하지 않고 그 단계에서 복구한 뒤 계속 진행합니다.")
