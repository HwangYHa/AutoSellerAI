from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from app.os.commerce_ops import apply_match_rules, build_supplier_order_csv, set_shipment_deadline, set_shipment_hold
from app.os.commerce_suite import (
    get_seller_tool_dashboard,
    save_channel_template,
    save_inventory_policy,
    save_order_work_meta,
)
from app.os.schema import ensure_os_schema
from app.os.tasks import enqueue_task

st.set_page_config(page_title="통합 판매 운영센터", page_icon="🧭", layout="wide")
ensure_os_schema()

st.title("🧭 통합 판매 운영센터")
st.caption("상품·주문·재고·CS·송장·정산을 한 화면에서 관리하는 AutoSellerAI 운영 허브")

data = get_seller_tool_dashboard(limit=700)
m = data["metrics"]
im = data["inventory_metrics"]

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("주문품목", m["total"])
c2.metric("상품 미매칭", m["unmatched"])
c3.metric("출고 보류", m["held"])
c4.metric("배송 지연", m["delayed"])
c5.metric("송장 대기", m["invoice_pending"])
c6.metric("품절 후보", im["soldout_candidates"])

orders_tab, inventory_tab, claims_tab, settlement_tab, template_tab = st.tabs(
    ["📦 주문·CS", "📉 재고·자동품절", "↩️ 클레임·매칭", "💰 정산 캘린더", "🧩 판매 템플릿"]
)

with orders_tab:
    st.caption("사용자 태그, 담당자, 우선순위, CS 메모, 사은품, 출고보류를 주문품목 단위로 관리합니다.")
    rows = data["rows"]
    if not rows:
        st.info("수집된 주문이 없습니다.")
    else:
        st.dataframe([
            {
                "선택ID": x["order_item_id"], "채널": x["platform"], "주문번호": x["order_no"],
                "상품": x["product_name"], "수량": x["quantity"], "상태": x["item_status"],
                "태그": x["user_tag"], "담당": x["owner"], "우선순위": x["priority"],
                "보류": x["shipment_hold"], "지연": x["delayed"], "클레임": x["claim_active"],
                "송장": x["tracking_number"] or "-", "채널반영": x["invoice_registered"],
            }
            for x in rows
        ], use_container_width=True, hide_index=True)

        ids = [int(x["order_item_id"]) for x in rows]
        selected = st.multiselect("작업할 주문품목 ID", ids)
        if selected:
            a, b, c = st.columns(3)
            if a.button("출고 보류", use_container_width=True):
                reason = "통합운영센터 수동 보류"
                r = set_shipment_hold(selected, hold=True, reason=reason)
                st.success(f"{r['updated']}건 보류")
                st.rerun()
            if b.button("보류 해제", use_container_width=True):
                r = set_shipment_hold(selected, hold=False)
                st.success(f"{r['updated']}건 해제")
                st.rerun()
            if c.button("24시간 출고기한", use_container_width=True):
                r = set_shipment_deadline(selected, hours_from_now=24)
                st.success(f"{r['updated']}건 출고기한 설정")
                st.rerun()

            csv_text = build_supplier_order_csv(selected)
            st.download_button("공급처 발주 CSV 다운로드", data=csv_text.encode("utf-8-sig"), file_name="supplier_orders.csv", mime="text/csv")

        st.markdown("#### 주문 업무 메타정보")
        item_id = st.selectbox("주문품목", ids, key="ops_meta_item")
        current = next(x for x in rows if int(x["order_item_id"]) == int(item_id))
        a, b, c = st.columns(3)
        tag = a.text_input("사용자 태그", value=current["user_tag"], placeholder="VIP / 긴급 / 교환주의")
        owner = b.text_input("담당자", value=current["owner"], placeholder="홍길동")
        priority = c.number_input("우선순위 (낮을수록 먼저)", min_value=0, max_value=999, value=int(current["priority"]))
        cs_memo = st.text_area("CS 메모", value=current["cs_memo"], height=100)
        gift_note = st.text_input("사은품/동봉 메모", value=current["gift_note"])
        checked = st.checkbox("교차 확인 완료", value=bool(current["checked"]))
        if st.button("업무정보 저장", type="primary"):
            save_order_work_meta(item_id, user_tag=tag, owner=owner, priority=priority, cs_memo=cs_memo, gift_note=gift_note, checked=checked)
            st.success("저장했습니다.")
            st.rerun()

with inventory_tab:
    st.caption("공급처 재고를 바탕으로 안전재고와 예약수량을 적용하여 품절 후보를 판정합니다. 외부 판매중지는 별도 승인계층을 거칩니다.")
    inv = data["inventory"]
    st.dataframe([
        {
            "상품ID": x["product_id"], "SKU": x["sku"], "상품": x["name"], "공급처재고": x["available_stock"],
            "안전재고": x["safety_stock"], "예약": x["reserved_qty"], "판매가능재고": x["effective_available"],
            "자동품절정책": x["auto_soldout"], "재고미확인": x["stock_unknown"], "품절후보": x["soldout_candidate"],
        }
        for x in inv
    ], use_container_width=True, hide_index=True)
    if inv:
        product_id = st.selectbox("재고 정책 상품", [x["product_id"] for x in inv])
        cur = next(x for x in inv if int(x["product_id"]) == int(product_id))
        a, b, c, d = st.columns(4)
        safety = a.number_input("안전재고", min_value=0, value=int(cur["safety_stock"]))
        reserved = b.number_input("예약수량", min_value=0, value=int(cur["reserved_qty"]))
        auto_soldout = c.checkbox("자동품절 대상 판정", value=bool(cur["auto_soldout"]))
        sellable = d.checkbox("판매 가능", value=bool(cur["sellable"]))
        note = st.text_input("정책 메모", value=cur["note"])
        if st.button("재고 정책 저장", type="primary"):
            r = save_inventory_policy(product_id, safety_stock=safety, reserved_qty=reserved, auto_soldout=auto_soldout, sellable=sellable, note=note)
            st.success("저장했습니다.") if r.get("ok") else st.error(r.get("error"))
            st.rerun()

with claims_tab:
    a, b = st.columns(2)
    if a.button("상품 매칭 규칙 적용", type="primary", use_container_width=True):
        r = apply_match_rules()
        st.success(f"{r['matched']}건 매칭 / {r['skipped']}건 미매칭")
        st.rerun()
    if b.button("주문·클레임 다시 수집", use_container_width=True):
        r = enqueue_task("order_sync", {"hours": 72}, queue_name="sync", dedupe_key="order_sync")
        st.success(f"작업 #{r['task_id']} 접수") if r.get("ok") else st.error(r.get("error"))
    st.markdown("#### 취소·반품·교환")
    st.dataframe(data["claims"], use_container_width=True, hide_index=True) if data["claims"] else st.info("수집된 클레임이 없습니다.")
    st.markdown("#### SKU/상품 매칭 규칙")
    st.dataframe(data["rules"], use_container_width=True, hide_index=True) if data["rules"] else st.info("등록된 매칭 규칙이 없습니다.")

with settlement_tab:
    st.caption("정산 원장을 일자별로 묶어 매출·순이익·정산확정 건수를 확인합니다.")
    cal = data["settlement_calendar"]
    if cal:
        st.dataframe(cal, use_container_width=True, hide_index=True)
        st.bar_chart({x["date"]: x["profit_krw"] for x in reversed(cal)})
    else:
        st.info("정산 데이터가 없습니다.")

with template_tab:
    st.caption("쇼핑몰별 반복 입력값을 템플릿으로 저장합니다. 상품등록 파이프라인에서 재사용할 수 있는 운영 데이터입니다.")
    if data["templates"]:
        st.dataframe(data["templates"], use_container_width=True, hide_index=True)
    a, b = st.columns(2)
    platform = a.selectbox("판매채널", ["coupang", "smartstore"])
    name = b.text_input("템플릿 이름", placeholder="식품 기본 / 생활용품 기본")
    category_hint = st.text_input("카테고리 힌트")
    shipping_fee = st.number_input("기본 배송비", min_value=0, value=3000, step=500)
    return_fee = st.number_input("기본 반품비", min_value=0, value=3000, step=500)
    if st.button("템플릿 저장", type="primary"):
        r = save_channel_template(platform=platform, name=name, category_hint=category_hint, values={"shipping_fee": shipping_fee, "return_fee": return_fee})
        st.success("저장했습니다.") if r.get("ok") else st.error(r.get("error"))
        if r.get("ok"):
            st.rerun()

st.divider()
st.info("플레이오토와 동일 제품을 복제하는 것이 아니라, 확인 가능한 운영 패턴을 AutoSellerAI의 기존 주문·발주·정산·안전 게이트 구조에 맞게 통합한 화면입니다.")
