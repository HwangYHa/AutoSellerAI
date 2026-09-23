from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import streamlit as st

from app.pricing.models import ensure_pricing_schema
from app.pricing.service import (
    PriceRow,
    apply_many,
    apply_price,
    get_policy,
    list_fee_rules,
    load_price_rows,
    price_change_history,
    save_fee_rule,
    save_policy,
)


st.set_page_config(page_title="판매가·마진 최적화 | AutoSellerAI", page_icon="💰", layout="wide")
ensure_pricing_schema()

st.title("💰 판매가·마진 최적화")
st.caption(
    "도매가와 쿠팡·네이버 현재 판매가를 비교해 목표 마진을 계산하고, "
    "사용자가 승인한 상품만 가격을 수정합니다."
)

policy = get_policy()

with st.expander("⚙️ 가격 정책", expanded=True):
    a, b, c, d = st.columns(4)
    target_margin = a.number_input("목표 순마진율 (%)", 1.0, 80.0, float(policy.target_margin_rate * 100), 0.5)
    coupang_fee = b.number_input("쿠팡 fallback 수수료 (%)", 0.0, 50.0, float(policy.coupang_fallback_fee_rate * 100), 0.1)
    smart_fee = c.number_input("스마트스토어 fallback 수수료 (%)", 0.0, 50.0, float(policy.smartstore_fallback_fee_rate * 100), 0.1)
    rounding = d.selectbox("가격 끝자리/올림", [900, 500, 100, 10], index=[900, 500, 100, 10].index(int(policy.rounding_unit)))
    e, f = st.columns(2)
    down = e.number_input("쿠팡 자동가격 가드 · 하락 허용 (%)", 0.0, 50.0, float(policy.coupang_auto_down_pct), 0.5)
    up = f.number_input("쿠팡 자동가격 가드 · 상승 허용 (%)", 0.0, 100.0, float(policy.coupang_auto_up_pct), 0.5)
    st.info(
        "권장가 = 도매가 ÷ (1 - 수수료율 - 목표마진율). "
        "가격 끝자리 적용 시 목표 마진을 깨지 않도록 올림합니다. "
        "쿠팡 ±%는 현재 공개 API에서 Wing 자동가격조정 설정 엔드포인트가 확인되지 않아 "
        "AutoSellerAI의 안전 가드 범위로 저장합니다."
    )
    if st.button("💾 가격 정책 저장", type="primary"):
        save_policy(
            target_margin_rate=target_margin / 100,
            coupang_fallback_fee_rate=coupang_fee / 100,
            smartstore_fallback_fee_rate=smart_fee / 100,
            rounding_unit=int(rounding),
            coupang_auto_down_pct=down,
            coupang_auto_up_pct=up,
        )
        st.success("가격 정책을 저장했습니다.")
        st.rerun()

with st.expander("🧾 카테고리별 수수료 규칙"):
    st.caption(
        "최근 실제 주문 수수료가 있으면 그것을 우선 사용합니다. "
        "없을 때 이 규칙을 사용하고, 규칙도 없으면 위 fallback 수수료를 '추정'으로 사용합니다."
    )
    c1, c2, c3, c4 = st.columns([1, 2, 1, 2])
    fee_platform = c1.selectbox("판매처", ["coupang", "smartstore"], format_func=lambda x: "쿠팡" if x == "coupang" else "스마트스토어")
    fee_category = c2.text_input("카테고리 코드/키")
    fee_rate_pct = c3.number_input("수수료 (%)", 0.0, 50.0, 10.8, 0.1)
    fee_note = c4.text_input("메모", placeholder="공식 공지/정산 확인 등")
    if st.button("수수료 규칙 저장"):
        try:
            save_fee_rule(fee_platform, fee_category, fee_rate_pct / 100, fee_note)
            st.success("저장했습니다.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    rules = list_fee_rules()
    if rules:
        st.dataframe(pd.DataFrame(rules), use_container_width=True, hide_index=True)

st.divider()
left, right = st.columns([1, 3])
with left:
    live = st.checkbox("마켓 API에서 현재 판매가 새로 읽기", value=True)
    if st.button("🔄 도매가 + 마켓 판매가 불러오기", type="primary", use_container_width=True):
        with st.spinner("쿠팡·네이버 판매가와 도매가를 비교하는 중입니다..."):
            try:
                rows = load_price_rows(live=live)
                st.session_state["pricing_rows"] = [x.to_dict() for x in rows]
                st.success(f"{len(rows)}개 판매채널 상품을 불러왔습니다.")
            except Exception as exc:
                st.error(f"가격 비교 불러오기 실패: {exc}")

raw_rows = st.session_state.get("pricing_rows", [])
if not raw_rows:
    st.info("먼저 ‘도매가 + 마켓 판매가 불러오기’를 실행하세요.")
    st.stop()

rows = [PriceRow(**x) for x in raw_rows]
eligible_count = sum(1 for x in rows if x.eligible)
missing_cost = sum(1 for x in rows if x.supply_price <= 0)
risk_count = sum(1 for x in rows if x.eligible and x.current_margin_rate < policy.target_margin_rate)

m1, m2, m3, m4 = st.columns(4)
m1.metric("전체 판매상품", len(rows))
m2.metric("가격 수정 가능", eligible_count)
m3.metric("도매가 미확인", missing_cost)
m4.metric("목표마진 미달", risk_count)

platform_filter = st.multiselect("판매처", ["coupang", "smartstore"], default=["coupang", "smartstore"], format_func=lambda x: "쿠팡" if x == "coupang" else "스마트스토어")
search = st.text_input("상품 검색", placeholder="상품명 검색")
only_risk = st.checkbox("목표마진 미달 상품만", value=False)

filtered = [
    x for x in rows
    if x.platform in platform_filter
    and (not search or search.lower() in x.name.lower())
    and (not only_risk or (x.eligible and x.current_margin_rate < policy.target_margin_rate))
]

table = []
for x in filtered:
    table.append({
        "선택": False,
        "listing_id": x.listing_id,
        "판매처": "쿠팡" if x.platform == "coupang" else "스마트스토어",
        "상품명": x.name,
        "도매가": int(x.supply_price),
        "도매가 출처": x.supply_source,
        "현재 판매가": int(x.current_price),
        "수수료(%)": round(x.fee_rate * 100, 2),
        "수수료 출처": x.fee_source,
        "현재마진(%)": round(x.current_margin_rate * 100, 2),
        "권장 판매가": int(x.target_price),
        "변경액": int(x.delta),
        "쿠팡 가드 최저": int(x.auto_floor_price),
        "쿠팡 가드 최고": int(x.auto_ceiling_price),
        "상태": "수정 가능" if x.eligible else (x.warning or "확인 필요"),
    })

edited = st.data_editor(
    pd.DataFrame(table),
    use_container_width=True,
    hide_index=True,
    disabled=[x for x in table[0].keys() if x != "선택"] if table else [],
    column_config={"선택": st.column_config.CheckboxColumn("선택", default=False)},
)

row_map = {x.listing_id: x for x in filtered}
selected_ids = [int(v) for v in edited.loc[edited["선택"] == True, "listing_id"].tolist()] if not edited.empty else []
selected = [row_map[x] for x in selected_ids if x in row_map and row_map[x].eligible]

st.caption(
    "도매가 미확인, 현재 판매가 미확인, 비정상 수수료 상품은 일괄 변경에서 자동 제외됩니다. "
    "동일 상품명으로 도매가를 찾은 경우 ‘도매가 출처’에서 확인할 수 있습니다."
)

st.subheader("승인 · 적용")
confirm = st.checkbox("현재가 → 권장가 변경 내용을 확인했고 실제 판매처 가격 수정을 승인합니다.")

c1, c2, c3 = st.columns(3)
with c1:
    one_id = st.selectbox(
        "개별 상품",
        [x.listing_id for x in filtered if x.eligible],
        format_func=lambda i: f"#{i} · {row_map[i].name[:55]}" if i in row_map else str(i),
    ) if any(x.eligible for x in filtered) else None
    if st.button("이 상품만 적용", use_container_width=True, disabled=not confirm or one_id is None):
        result = apply_price(row_map[int(one_id)])
        st.success(f"가격 수정 완료: {result.get('price'):,.0f}원") if result.get("ok") else st.error(result.get("error"))
with c2:
    if st.button(f"선택 {len(selected)}개 적용", use_container_width=True, disabled=not confirm or not selected):
        with st.spinner("선택 상품 가격을 수정 중입니다..."):
            result = apply_many(selected)
        st.success(f"성공 {result['success']} / 실패 {result['failed']}")
        if result["failed"]:
            st.error([x.get("error") for x in result["results"] if not x.get("ok")][:10])
with c3:
    all_eligible = [x for x in filtered if x.eligible]
    if st.button(f"현재 필터의 적격 {len(all_eligible)}개 전체 적용", use_container_width=True, disabled=not confirm or not all_eligible):
        with st.spinner("전체 적격 상품 가격을 순차 수정 중입니다..."):
            result = apply_many(all_eligible)
        st.success(f"성공 {result['success']} / 실패 {result['failed']}")
        if result["failed"]:
            st.error([x.get("error") for x in result["results"] if not x.get("ok")][:10])

st.divider()
st.subheader("🧾 가격 변경 이력")
history = price_change_history(200)
if history:
    st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)
else:
    st.caption("아직 가격 변경 이력이 없습니다.")
