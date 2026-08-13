"""AutoSellerAI 8단계 원큐 운영 화면."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st

from app.orchestration.oneclick import get_process_status, get_next_stage, run_safe_oneclick
from app.policies.runtime_patch import apply_fulfillment_policy_patch
from gui.korean_runtime import apply_korean_patch

apply_korean_patch()
apply_fulfillment_policy_patch()

st.set_page_config(page_title="원큐 운영 | 오토셀러 AI", page_icon="🚀", layout="wide")

st.markdown("# 🚀 원큐 운영")
st.caption("복잡했던 15개 세부단계를 8개의 실제 업무 단위로 통합했습니다.")
st.info(
    "**연결 → 상품 확보 → 판매 준비 → 채널 등록 → 주문 → 발주/배송 → 정산 → 성장** 순서만 기억하면 됩니다. "
    "조회·동기화는 자동 실행하고, 실제 상품등록과 공급처 발주는 반드시 사용자 승인 후 실행합니다."
)

status = get_process_status()

st.markdown("### ⚡ 안전 자동 실행")
left, right = st.columns([2.4, 1])
with left:
    st.write("쿠팡·스마트스토어 기존상품 읽기 → DB 동기화 → 공급처 원본 이미지 보완을 실행합니다. 외부 판매상품 생성이나 실제 발주는 하지 않습니다.")
with right:
    run_clicked = st.button("▶ 안전 작업 실행", type="primary", use_container_width=True)

if run_clicked:
    with st.spinner("판매채널 동기화와 이미지 보완을 진행 중입니다..."):
        result = run_safe_oneclick()
    st.session_state["oneclick_last_result"] = result
    status = result.get("status") or get_process_status()

last_result = st.session_state.get("oneclick_last_result")
if last_result:
    if last_result.get("ok"):
        st.success("실행 가능한 안전 작업을 완료했습니다.")
    else:
        st.warning("일부 연결은 실패했습니다. 성공한 채널 결과는 유지됩니다. 실패한 연동만 확인하세요.")
    for step in last_result.get("steps", []):
        label = "✅" if step.get("ok") else "❌"
        with st.expander(f"{label} {step.get('key')}", expanded=not step.get("ok")):
            st.json(step.get("result") if step.get("ok") else {"error": step.get("error")})

progress = float(status.get("progress", 0.0))
st.progress(
    progress,
    text=f"필수 운영 진행도 {status.get('completed_required', 0)}/{status.get('required_total', 0)} · {progress*100:.0f}%",
)

counts = status.get("counts", {})
a, b, c, d = st.columns(4)
a.metric("상품", counts.get("products", 0))
b.metric("판매채널 등록", counts.get("listings", 0))
c.metric("주문", counts.get("platform_orders", 0))
d.metric("정산", counts.get("financial_orders", 0))

st.markdown("### 🧭 8단계 운영 흐름")
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
        cols = st.columns([0.7, 5.3, 1.4], vertical_alignment="center")
        cols[0].markdown(f"### {row['order']:02d}")
        with cols[1]:
            st.markdown(f"**{row['title']}** · {badge}")
            st.caption(row["description"])
            flags = []
            if row.get("safe_auto"):
                flags.append("자동화 가능")
            if row.get("approval_required"):
                flags.append("실행 전 승인")
            if row.get("optional"):
                flags.append("선택")
            if flags:
                st.caption(" · ".join(flags))
        cols[2].page_link(row["page"], label="열기", icon="➡️", use_container_width=True)

next_stage = get_next_stage(status)
st.markdown("### 🎯 다음 한 가지")
if next_stage:
    with st.container(border=True):
        left, right = st.columns([4, 1.2], vertical_alignment="center")
        with left:
            st.markdown(f"#### {next_stage['order']:02d}. {next_stage['title']}")
            st.write(next_stage["description"])
            if next_stage.get("approval_required"):
                st.warning("외부 상태 또는 비용이 바뀌는 단계입니다. Seller OS에서 대상과 금액을 확인한 뒤 실행하세요.")
        right.page_link(next_stage["page"], label="다음 작업", icon="🚀", use_container_width=True)
else:
    st.success("필수 운영 단계가 완료 상태입니다. Seller OS에서 상품·주문·수익을 관리하세요.")

st.caption("운영 원칙: 실패한 연결이나 단계만 복구하고, 이미 완료된 작업은 반복 입력하지 않습니다.")
