from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from app.os.fulfillment_monitor import get_fulfillment_monitor
from app.os.tasks import enqueue_task
from gui.korean_runtime import apply_korean_patch

apply_korean_patch()
st.set_page_config(page_title="AutoSellerAI · 주문·발주 관제센터", page_icon="🛰️", layout="wide")


def _krw(v) -> str:
    return f"{int(v or 0):,}원"


def _dt(v) -> str:
    if not v:
        return "-"
    try:
        return v.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(v).replace("T", " ")[:16]


st.markdown("# 🛰️ 주문 · 발주 관제센터")
st.caption("쿠팡/스마트스토어 주문 → 공급처 발주 → 결제 → 송장 → 판매채널 반영을 한 화면에서 추적합니다.")

left, right = st.columns([5, 1])
with right:
    if st.button("자동화 1회 실행", type="primary", use_container_width=True):
        result = enqueue_task("fulfillment_cycle", {}, queue_name="sync", dedupe_key="fulfillment_cycle")
        if result.get("ok"):
            st.success(f"작업 #{result['task_id']} 접수")
        else:
            st.error(result.get("error", "작업 접수 실패"))

monitor = get_fulfillment_monitor(limit=1000)
m = monitor["metrics"]
policy = monitor["policy"]

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.metric("신규", m["new"])
c2.metric("발주 승인대기", m["approval_wait"])
c3.metric("결제/발주 처리", m["payment_wait"])
c4.metric("공급처 발주완료", m["ordered"])
c5.metric("송장 대기", m["tracking_wait"])
c6.metric("채널 송장반영", m["tracking_done"])
c7.metric("예외", m["exceptions"])

if not monitor["payment_model"]["interactive_card_supported"]:
    st.warning(
        "카드사 앱 사용자 승인 단계는 아직 별도 Payment 상태로 구현되지 않았습니다. "
        "현재 '결제/발주 처리'는 공급처 주문 실행 상태이며, 카드앱 승인형 결제는 다음 Payment Orchestrator에서 분리됩니다."
    )

with st.expander("자동화 정책", expanded=False):
    a, b, c, d, e = st.columns(5)
    a.metric("자동발주/결제", "ON" if policy["auto_purchase_enabled"] else "OFF")
    b.metric("송장 자동반영", "ON" if policy["auto_tracking_enabled"] else "OFF")
    c.metric("확인 주기", f"{policy['poll_interval_seconds']}초")
    d.metric("자동발주 한도", _krw(policy["max_order_krw"]))
    e.metric("최소 이익", _krw(policy["min_profit_krw"]))
    st.caption(f"최소 마진율 {policy['min_margin_pct']:.1%} · 허용 공급처: {policy['supplier_allowlist'] or '검증 driver 전체'}")

rows = monitor["rows"]
if not rows:
    st.info("수집된 주문 품목이 없습니다.")
    st.stop()

f1, f2, f3 = st.columns([1.3, 1.4, 2.3])
platform = f1.selectbox("판매채널", ["전체", "coupang", "smartstore"])
stage = f2.selectbox("처리 단계", ["전체", "신규", "승인대기", "결제/발주", "송장대기", "완료", "예외"])
keyword = f3.text_input("검색", placeholder="주문번호 · 상품명 · 공급처 · 송장번호")


def include(row: dict) -> bool:
    if platform != "전체" and row["platform"] != platform:
        return False
    if keyword:
        hay = " ".join([
            row["order_no"], row["product_name"], row["supplier_code"],
            row["supplier_order_id"], row["tracking_number"], row["receiver_name"],
        ]).lower()
        if keyword.lower() not in hay:
            return False
    if stage == "신규" and row["item_status"] != "new":
        return False
    if stage == "승인대기" and row["payment_code"] != "approval_wait":
        return False
    if stage == "결제/발주" and row["payment_code"] not in {"payment_ready", "payment_processing"}:
        return False
    if stage == "송장대기" and row["tracking_code"] not in {"waiting_tracking", "tracking_ready"}:
        return False
    if stage == "완료" and row["tracking_code"] != "marketplace_done":
        return False
    if stage == "예외" and not row["error"]:
        return False
    return True

filtered = [x for x in rows if include(x)]

st.markdown("### 처리 현황")
st.dataframe([
    {
        "주문시각": _dt(x["ordered_at"]),
        "채널": x["platform"],
        "주문번호": x["order_no"],
        "상품": x["product_name"],
        "수량": x["quantity"],
        "판매금액": x["sale_amount_krw"],
        "공급처": x["supplier_code"] or "미연결",
        "공급처발주번호": x["supplier_order_id"] or "-",
        "결제/발주": x["payment_label"],
        "송장": x["tracking_label"],
        "택배사": x["delivery_company"] or "-",
        "송장번호": x["tracking_number"] or "-",
        "Driver": "검증완료" if x["driver_can_order"] else "확인필요",
        "예외": x["error"],
    }
    for x in filtered
], use_container_width=True, hide_index=True)

st.markdown("### 주문별 상세 흐름")
for x in filtered[:100]:
    title = f"{x['platform'].upper()} · {x['order_no']} · {x['product_name'][:55]}"
    with st.expander(title):
        a, b, c, d, e = st.columns(5)
        a.metric("판매금액", _krw(x["sale_amount_krw"]))
        b.metric("예상 공급비용", _krw(x["expected_cost_krw"]))
        c.metric("공급처", x["supplier_code"] or "미연결")
        d.metric("결제/발주", x["payment_label"])
        e.metric("송장", x["tracking_label"])
        st.write(
            f"주문수집 ✅  → 공급처 {'✅' if x['supplier_code'] else '⏳'}  → "
            f"발주/결제 {'✅' if x['supplier_order_id'] else '⏳'}  → "
            f"송장 {'✅' if x['tracking_number'] else '⏳'}  → "
            f"판매채널 반영 {'✅' if x['invoice_registered'] else '⏳'}"
        )
        st.caption(
            f"수취인 {x['receiver_name'] or '-'} · 공급처 Driver: "
            f"{'실제 발주 가능' if x['driver_can_order'] else x['driver_note'] or '미검증'}"
        )
        if x["error"]:
            st.error(x["error"])
