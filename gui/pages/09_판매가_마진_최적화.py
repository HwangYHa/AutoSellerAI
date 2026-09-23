from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import streamlit as st

from app.pricing.models import ensure_pricing_schema
from app.pricing.approval_queue import dismiss_approval, list_approval_queue
from app.os.commerce_automation import get_automation_dashboard, save_scheduler_rule
from app.os.tasks import enqueue_task
from app.pricing.change_control import (
    apply_guarded_batch,
    batch_history,
    preview_price_changes,
    rollback_batch,
    rollback_candidates,
    rollback_change,
    rollback_history,
)
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
st.subheader("⏱️ 정기 가격·마진 감시")
dashboard = get_automation_dashboard()
pricing_rule = next((x for x in dashboard["scheduler_rules"] if x["task_type"] == "pricing_watch"), None)
if pricing_rule:
    s1, s2, s3 = st.columns([1, 1, 2])
    watch_enabled = s1.checkbox("정기 감시 활성화", value=bool(pricing_rule["enabled"]))
    watch_hours = s2.number_input("감시 주기(시간)", min_value=1, max_value=168, value=max(1, int(pricing_rule["interval_minutes"]) // 60))
    max_supplier_items = s3.number_input(
        "1회 도매가 최신화 최대 상품수",
        min_value=50,
        max_value=5000,
        value=int((pricing_rule.get("payload") or {}).get("max_supplier_items", 500)),
        step=50,
    )
    a1, a2 = st.columns(2)
    if a1.button("감시 설정 저장", use_container_width=True):
        r = save_scheduler_rule(
            "pricing_watch",
            int(watch_hours) * 60,
            enabled=watch_enabled,
            queue_name="sync",
            payload={"max_supplier_items": int(max_supplier_items), "live": True},
            description="도매가·마진 위험 감시 → 승인대기열 + 알림",
        )
        st.success("정기 감시 설정을 저장했습니다.") if r.get("ok") else st.error(r.get("error"))
        if r.get("ok"):
            st.rerun()
    if a2.button("지금 감시 실행", type="primary", use_container_width=True):
        r = enqueue_task(
            "pricing_watch",
            {"max_supplier_items": int(max_supplier_items), "live": True},
            queue_name="sync",
            dedupe_key="manual:pricing_watch",
        )
        st.success(f"가격·마진 감시 작업 #{r['task_id']} 접수") if r.get("ok") else st.error(r.get("error"))
else:
    st.warning("pricing_watch 스케줄 규칙이 아직 생성되지 않았습니다. 재배포 후 새로고침하세요.")

pending_queue = list_approval_queue("pending", 500)
with st.expander(f"🛎️ 가격 승인 대기열 · {len(pending_queue)}건", expanded=bool(pending_queue)):
    if pending_queue:
        qdf = pd.DataFrame(pending_queue)
        st.dataframe(qdf, use_container_width=True, hide_index=True)
        queue_ids = st.multiselect(
            "검토할 승인대기 항목",
            [int(x["대기ID"]) for x in pending_queue],
            format_func=lambda qid: next(
                (f"#{qid} · {x['판매처']} · {x['위험']} · {x['상품명'][:50]}" for x in pending_queue if int(x["대기ID"]) == int(qid)),
                str(qid),
            ),
        )
        q1, q2 = st.columns(2)
        if q1.button("선택 위험상품 최신 재검증 후 불러오기", disabled=not queue_ids, use_container_width=True):
            listing_ids = {int(x["listing_id"]) for x in pending_queue if int(x["대기ID"]) in set(queue_ids)}
            with st.spinner("도매가·마켓 현재가를 다시 확인하는 중입니다..."):
                latest_rows = load_price_rows(live=True)
            chosen = [x for x in latest_rows if int(x.listing_id) in listing_ids]
            st.session_state["pricing_rows"] = [x.to_dict() for x in chosen]
            st.success(f"{len(chosen)}개 위험상품을 최신 상태로 불러왔습니다. 아래 Preview에서 검토하세요.")
            st.rerun()
        if q2.button("선택 항목 대기열에서 제외", disabled=not queue_ids, use_container_width=True):
            done = sum(1 for qid in queue_ids if dismiss_approval(int(qid)))
            st.success(f"{done}개 항목을 검토 제외 처리했습니다.")
            st.rerun()
    else:
        st.caption("현재 가격 승인 대기 항목이 없습니다.")

st.info("정기 감시는 도매가·마켓 현재가를 읽고 위험상품을 승인 대기열에 올리며 알림만 전송합니다. 판매가격은 자동 변경하지 않습니다.")

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

st.subheader("🧪 변경 전 Preview")
all_eligible = [x for x in filtered if x.eligible]
preview_scope = st.radio(
    "Preview 범위",
    ["선택 상품", "현재 필터 전체"],
    horizontal=True,
    index=0 if selected else 1,
)
preview_rows = selected if preview_scope == "선택 상품" else filtered
preview = preview_price_changes(preview_rows) if preview_rows else {
    "summary": {"total": 0, "increase": 0, "decrease": 0, "unchanged": 0, "sensitive": 0, "blocked": 0, "sales_history": 0},
    "items": [],
    "requires_extra_confirmation": False,
}
ps = preview["summary"]
p1, p2, p3, p4, p5, p6 = st.columns(6)
p1.metric("Preview 대상", ps["total"])
p2.metric("인상", ps["increase"])
p3.metric("인하", ps["decrease"])
p4.metric("추가승인 필요", ps["sensitive"])
p5.metric("판매이력 있음", ps["sales_history"])
p6.metric("적용 차단", ps["blocked"])

if preview["items"]:
    preview_df = pd.DataFrame([
        {
            "판매처": "쿠팡" if x["platform"] == "coupang" else "스마트스토어",
            "상품명": x["name"],
            "현재가": int(x["before_price"]),
            "변경가": int(x["after_price"]),
            "변경액": int(x["delta"]),
            "변동률(%)": round(x["change_pct"], 2),
            "판매이력": x["sales_count"],
            "보호등급": x["guard_level"],
            "확인사유": x["guard_reason"],
        }
        for x in preview["items"]
    ])
    st.dataframe(preview_df, use_container_width=True, hide_index=True)

if preview["requires_extra_confirmation"]:
    st.warning(
        "20% 이상 인상, 10% 이상 인하 또는 판매이력 상품의 5% 이상 가격변경이 포함되어 있습니다. "
        "이 항목들은 일반 승인만으로는 적용되지 않습니다."
    )

st.subheader("승인 · 적용")
confirm = st.checkbox("현재가 → 권장가 변경 내용을 확인했고 실제 판매처 가격 수정을 승인합니다.")
sensitive_confirm = st.checkbox(
    "급격한 가격변동 및 판매이력 상품도 별도로 확인했고 적용을 승인합니다.",
    help="20% 이상 인상, 10% 이상 인하, 또는 판매이력 상품의 5% 이상 변경에 대한 추가 승인입니다.",
)

c1, c2, c3 = st.columns(3)
with c1:
    one_id = st.selectbox(
        "개별 상품",
        [x.listing_id for x in filtered if x.eligible],
        format_func=lambda i: f"#{i} · {row_map[i].name[:55]}" if i in row_map else str(i),
    ) if any(x.eligible for x in filtered) else None
    if st.button("이 상품만 적용", use_container_width=True, disabled=not confirm or one_id is None):
        one_rows = [row_map[int(one_id)]]
        one_preview = preview_price_changes(one_rows)
        result = apply_guarded_batch(
            one_rows,
            mode="single",
            allow_sensitive=sensitive_confirm,
        )
        if result.get("needs_confirmation"):
            st.error(result["error"])
        elif result.get("success"):
            st.success(f"가격 수정 완료 · 배치 {result.get('batch_key', '')[:10]} · 성공 {result['success']}")
        else:
            st.error([x.get("error") for x in result.get("results", []) if not x.get("ok")] or result.get("error"))
with c2:
    if st.button(f"선택 {len(selected)}개 적용", use_container_width=True, disabled=not confirm or not selected):
        with st.spinner("선택 상품 가격을 수정 중입니다..."):
            result = apply_guarded_batch(
                selected,
                mode="selected",
                allow_sensitive=sensitive_confirm,
            )
        if result.get("needs_confirmation"):
            st.error(result["error"])
        else:
            st.success(f"성공 {result['success']} / 실패 {result['failed']} / 차단 {result['blocked']} · 배치 {result.get('batch_key', '')[:10]}")
            if result["failed"] or result["blocked"]:
                st.error([x.get("error") for x in result["results"] if not x.get("ok")][:10])
with c3:
    if st.button(f"현재 필터의 적격 {len(all_eligible)}개 전체 적용", use_container_width=True, disabled=not confirm or not all_eligible):
        with st.spinner("전체 적격 상품 가격을 순차 수정 중입니다..."):
            result = apply_guarded_batch(
                all_eligible,
                mode="filtered_all",
                allow_sensitive=sensitive_confirm,
            )
        if result.get("needs_confirmation"):
            st.error(result["error"])
        else:
            st.success(f"성공 {result['success']} / 실패 {result['failed']} / 차단 {result['blocked']} · 배치 {result.get('batch_key', '')[:10]}")
            if result["failed"] or result["blocked"]:
                st.error([x.get("error") for x in result["results"] if not x.get("ok")][:10])

st.divider()
st.subheader("↩️ 가격 롤백")
st.caption(
    "롤백 직전 판매처의 현재가를 다시 조회합니다. 현재가가 해당 변경의 '변경후 가격'과 다르면 "
    "판매자센터에서 별도 수정된 것으로 보고 자동 롤백을 차단합니다."
)
candidates = rollback_candidates(100)
if candidates:
    rollback_df = pd.DataFrame(candidates)
    st.dataframe(rollback_df, use_container_width=True, hide_index=True)
    rollback_log_id = st.selectbox(
        "개별 롤백 대상",
        [int(x["로그ID"]) for x in candidates],
        format_func=lambda log_id: next(
            (
                f"#{log_id} · {x['판매처']} · {x['상품명'][:45]} · "
                f"{x['변경후']:,.0f} → {x['변경전']:,.0f}원"
                for x in candidates if int(x["로그ID"]) == int(log_id)
            ),
            str(log_id),
        ),
    )
    rollback_confirm = st.checkbox("선택한 가격 변경을 이전 가격으로 복원하는 것을 승인합니다.")
    if st.button("선택 변경 롤백", disabled=not rollback_confirm):
        with st.spinner("현재 판매가를 재확인한 뒤 롤백하는 중입니다..."):
            rb = rollback_change(int(rollback_log_id))
        if rb.get("ok"):
            st.success(f"롤백 완료 · {rb['restored_price']:,.0f}원")
        else:
            st.error(rb.get("error"))
else:
    st.caption("현재 롤백 가능한 성공 가격변경 이력이 없습니다.")

batches = batch_history(30)
if batches:
    with st.expander("배치 전체 롤백"):
        st.dataframe(pd.DataFrame(batches), use_container_width=True, hide_index=True)
        rollback_batch_key = st.selectbox("롤백할 배치", [x["배치ID"] for x in batches])
        batch_rb_confirm = st.checkbox("이 배치에서 성공한 가격변경 전체의 롤백을 승인합니다.")
        if st.button("배치 롤백 실행", disabled=not batch_rb_confirm):
            with st.spinner("배치의 각 상품 현재가를 검증하며 롤백 중입니다..."):
                rb = rollback_batch(str(rollback_batch_key))
            st.success(f"롤백 성공 {rb['success']} / 실패·차단 {rb['failed']}")
            if rb["failed"]:
                st.error([x.get("error") for x in rb["results"] if not x.get("ok")][:10])

rb_history = rollback_history(100)
if rb_history:
    with st.expander("롤백 이력"):
        st.dataframe(pd.DataFrame(rb_history), use_container_width=True, hide_index=True)

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
