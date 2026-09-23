from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import streamlit as st

from app.pricing.models import ensure_pricing_schema
from app.pricing.supply_monitor import (
    DEFAULT_MAX_SUPPLY_AGE_HOURS,
    classify_price_risk,
    list_supplier_mappings,
    persist_price_risks,
    rebuild_supplier_mappings,
    refresh_supplier_prices,
    supply_price_history,
)
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
st.subheader("🔗 도매가 최신화 · 상품 매핑")
st.caption(
    "가격 변경 전에 판매상품을 실제 도매 상품과 연결하고 최신 공급가를 다시 확인합니다. "
    f"마지막 성공 갱신이 {int(DEFAULT_MAX_SUPPLY_AGE_HOURS)}시간을 넘긴 상품은 가격 변경 대상에서 자동 차단됩니다."
)

mcol1, mcol2, mcol3 = st.columns([1, 1, 2])
with mcol1:
    if st.button("① 상품 매핑 재구축", use_container_width=True):
        with st.spinner("판매상품과 공급사 상품을 안전하게 매칭하는 중입니다..."):
            result = rebuild_supplier_mappings()
        st.session_state["supplier_mapping_result"] = result
        st.success(
            f"매칭 {result['matched']} / 미매칭 {result['unmatched']} · "
            f"신규 {result['created']} / 갱신 {result['updated']}"
        )
with mcol2:
    refresh_limit = st.number_input("이번 갱신 최대 상품수", min_value=1, max_value=5000, value=500, step=50)
    if st.button("② 매핑된 도매가 최신화", type="primary", use_container_width=True):
        with st.spinner("공급사 API에서 최신 공급가를 확인하는 중입니다..."):
            result = refresh_supplier_prices(max_items=int(refresh_limit))
        st.session_state["supplier_refresh_result"] = result
        st.success(
            f"갱신 {result['refreshed']} · 가격변동 {result['changed']} · "
            f"실패 {result['failed']} · 연동비활성 {result['unavailable']}"
        )
        if result.get("errors"):
            st.warning("\n".join(result["errors"][:8]))
with mcol3:
    st.info(
        "자동 매핑은 ① 공급사 원본 연결, ② 기존 공급사 워크플로우 연결, "
        "③ 정규화 상품명이 완전히 같고 후보가 1개뿐인 경우까지만 허용합니다. "
        "유사도(fuzzy) 추정 매칭은 판매가 자동수정에 사용하지 않습니다."
    )

mapping_rows = list_supplier_mappings()
with st.expander(f"도매 상품 매핑 현황 · {len(mapping_rows)}개"):
    if mapping_rows:
        st.dataframe(pd.DataFrame(mapping_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("아직 생성된 도매 상품 매핑이 없습니다.")

left, right = st.columns([1, 3])
with left:
    live = st.checkbox("마켓 API에서 현재 판매가 새로 읽기", value=True)
    if st.button("🔄 도매가 + 마켓 판매가 불러오기", type="primary", use_container_width=True):
        with st.spinner("쿠팡·네이버 판매가와 도매가를 비교하는 중입니다..."):
            try:
                rows = load_price_rows(live=live)
                st.session_state["pricing_rows"] = [x.to_dict() for x in rows]
                risk_counts = persist_price_risks(rows, get_policy().target_margin_rate)
                st.session_state["pricing_risk_counts"] = risk_counts
                st.success(
                    f"{len(rows)}개 판매채널 상품을 불러왔습니다. "
                    f"긴급 {risk_counts.get('CRITICAL', 0)} · 고위험 {risk_counts.get('HIGH', 0)} · "
                    f"마진미달 {risk_counts.get('WARNING', 0)} · 차단 {risk_counts.get('BLOCKED', 0)}"
                )
            except Exception as exc:
                st.error(f"가격 비교 불러오기 실패: {exc}")

raw_rows = st.session_state.get("pricing_rows", [])
if not raw_rows:
    st.info("먼저 ‘도매가 + 마켓 판매가 불러오기’를 실행하세요.")
    st.stop()

rows = [PriceRow(**x) for x in raw_rows]
eligible_count = sum(1 for x in rows if x.eligible)
missing_cost = sum(1 for x in rows if x.supply_price <= 0)
risk_count = sum(1 for x in rows if x.current_margin_rate < policy.target_margin_rate and x.supply_price > 0)
blocked_count = sum(1 for x in rows if not x.eligible)

m1, m2, m3, m4 = st.columns(4)
m1.metric("전체 판매상품", len(rows))
m2.metric("가격 수정 가능", eligible_count)
m3.metric("도매가 미확인", missing_cost)
m4.metric("목표마진 미달 / 차단", f"{risk_count} / {blocked_count}")

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
    risk_level, risk_reason = classify_price_risk(
        eligible=x.eligible,
        supply_price=x.supply_price,
        current_price=x.current_price,
        margin_rate=x.current_margin_rate,
        target_margin_rate=policy.target_margin_rate,
        supply_fresh=x.supply_fresh,
        supply_safe=x.supply_safe,
    )
    risk_label = {
        "CRITICAL": "🔴 적자",
        "HIGH": "🔴 고위험",
        "WARNING": "🟠 목표마진 미달",
        "OK": "🟢 정상",
        "REVIEW": "🔵 가격 경쟁력 검토",
        "BLOCKED": "⚫ 적용 차단",
    }.get(risk_level, risk_level)
    table.append({
        "선택": False,
        "listing_id": x.listing_id,
        "판매처": "쿠팡" if x.platform == "coupang" else "스마트스토어",
        "상품명": x.name,
        "도매가": int(x.supply_price),
        "도매가 출처": x.supply_source,
        "매핑": x.mapping_type or "-",
        "도매가 갱신경과(h)": round(x.supply_age_hours, 1) if x.supply_age_hours is not None else None,
        "현재 판매가": int(x.current_price),
        "수수료(%)": round(x.fee_rate * 100, 2),
        "수수료 출처": x.fee_source,
        "현재마진(%)": round(x.current_margin_rate * 100, 2),
        "권장 판매가": int(x.target_price),
        "변경액": int(x.delta),
        "쿠팡 가드 최저": int(x.auto_floor_price),
        "쿠팡 가드 최고": int(x.auto_ceiling_price),
        "위험": risk_label,
        "위험 사유": risk_reason,
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
    "도매가 미확인, 안전한 공급사 매핑 없음, 72시간 이상 공급가 미갱신, "
    "현재 판매가 미확인, 비정상 수수료 상품은 실제 가격 변경에서 자동 제외됩니다."
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
st.subheader("📉 도매가 변동 이력")
supply_history = supply_price_history(200)
if supply_history:
    st.dataframe(pd.DataFrame(supply_history), use_container_width=True, hide_index=True)
else:
    st.caption("아직 도매가 갱신 이력이 없습니다.")

st.divider()
st.subheader("🧾 가격 변경 이력")
history = price_change_history(200)
if history:
    st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)
else:
    st.caption("아직 가격 변경 이력이 없습니다.")
