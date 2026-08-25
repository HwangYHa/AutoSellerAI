from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from app.os.bulk_market_tools import (
    apply_bulk_product_xlsx,
    build_bulk_product_template_xlsx,
    stage_marketplace_clone,
)
from app.os.commerce_automation import (
    answer_inquiry,
    generate_ai_inquiry_draft,
    get_automation_dashboard,
    save_inquiry_template,
    save_scheduler_rule,
)
from app.os.drivers import list_supplier_driver_status
from app.os.payment_orchestrator import list_payment_sessions
from app.os.scheduler import ensure_default_scheduler_rules
from app.os.schema import ensure_os_schema
from app.os.tasks import enqueue_task

st.set_page_config(page_title="커머스 자동화 제어센터", page_icon="🤖", layout="wide")
ensure_os_schema()
ensure_default_scheduler_rules()

st.title("🤖 커머스 자동화 제어센터")
st.caption("클레임 · 문의 · 재고 · 정산 · 대량상품 · 마켓복제 · 스케줄러 · 카드승인 결제를 한 곳에서 제어합니다.")

controls = [
    ("주문", "order_sync", {"hours": 24}, "sync"),
    ("클레임", "claim_sync", {"hours": 24}, "sync"),
    ("문의", "inquiry_sync", {}, "sync"),
    ("재고 자동화", "inventory_automation", {"confirmations": 2}, "automation"),
    ("정산", "settlement_sync", {"days": 7}, "sync"),
    ("결제상태", "payment_sync", {"limit": 100}, "automation"),
]
cols = st.columns(len(controls))
for col, (label, task_type, payload, queue) in zip(cols, controls):
    if col.button(f"{label} 지금 실행", use_container_width=True, key=f"run_{task_type}"):
        r = enqueue_task(task_type, payload, queue_name=queue, dedupe_key=f"manual:{task_type}")
        if r.get("ok"):
            st.success(f"{label} 작업 #{r['task_id']} 접수")
        else:
            st.error(r.get("error", "작업 접수 실패"))

st.divider()
data = get_automation_dashboard()
payments = list_payment_sessions(limit=300)

open_inquiries = [x for x in data["inquiries"] if x["status"] != "answered"]
waiting_payments = [x for x in payments if x["status"] in {"awaiting_user", "authorizing"}]
a, b, c, d, e = st.columns(5)
a.metric("미답변 문의", len(open_inquiries))
b.metric("카드/결제 대기", len(waiting_payments))
c.metric("정산 수집", len(data["settlements"]))
d.metric("재고 감시 상품", len(data["inventory_states"]))
e.metric("스케줄 규칙", len(data["scheduler_rules"]))

inq_tab, inv_tab, settle_tab, bulk_tab, clone_tab, sched_tab, payment_tab = st.tabs([
    "💬 문의·AI 답변", "📉 품절·재입고", "💰 정산", "📊 엑셀 대량작업",
    "🔁 마켓 복제", "⏱️ 스케줄러", "💳 카드승인 결제",
])

with inq_tab:
    st.caption("상품문의와 구매자 고객문의를 자동수집합니다. AI는 초안만 만들고 실제 전송은 사용자가 확인 후 실행합니다.")
    if data["inquiries"]:
        st.dataframe([
            {
                "ID": x["id"], "채널": x["platform"], "구분": x["type"], "유형": x.get("category", ""),
                "제목": x.get("title", ""), "문의": x["question"], "상태": x["status"],
                "문의시각": x["asked_at"],
            }
            for x in data["inquiries"]
        ], use_container_width=True, hide_index=True)
        choices = {f"#{x['id']} · {x['platform']} · {x['type']} · {x['question'][:70]}": x for x in data["inquiries"]}
        selected = choices[st.selectbox("문의 선택", list(choices), key="auto_inquiry_select")]
        st.write(selected["question"])
        if st.button("AI 답변 초안 생성", key="ai_inquiry_draft"):
            r = generate_ai_inquiry_draft(int(selected["id"]))
            if r.get("ok"):
                st.session_state[f"inq_answer_{selected['id']}"] = r["draft"]
                st.rerun()
            else:
                st.error(r.get("error"))
        default_answer = st.session_state.get(f"inq_answer_{selected['id']}", selected.get("ai_draft") or selected.get("answer") or "")
        answer = st.text_area("전송할 답변", value=default_answer, height=160, key=f"answer_text_{selected['id']}")
        st.warning("답변 전송은 고객에게 실제 노출되는 외부 변경입니다. 내용 확인 후 실행하세요.")
        if st.button("검토한 답변 전송", type="primary", key=f"answer_send_{selected['id']}"):
            r = answer_inquiry(int(selected["id"]), answer, actor="seller")
            st.success("답변을 전송했습니다.") if r.get("ok") else st.error(r.get("error", "답변 전송 실패"))
            if r.get("ok"):
                st.rerun()
    else:
        st.info("수집된 문의가 없습니다.")

    st.markdown("#### 답변 템플릿")
    if data.get("inquiry_templates"):
        st.dataframe(data["inquiry_templates"], use_container_width=True, hide_index=True)
    t1, t2, t3 = st.columns(3)
    tpl_platform = t1.selectbox("템플릿 채널", ["all", "coupang", "smartstore"], key="inq_tpl_platform")
    tpl_key = t2.text_input("템플릿 키", placeholder="shipping-delay", key="inq_tpl_key")
    tpl_name = t3.text_input("템플릿 이름", placeholder="배송지연 안내", key="inq_tpl_name")
    tpl_category = st.text_input("문의 유형", placeholder="배송 / 반품 / 교환 / 상품", key="inq_tpl_category")
    tpl_body = st.text_area("템플릿 본문", height=120, key="inq_tpl_body")
    if st.button("답변 템플릿 저장", key="inq_tpl_save"):
        r = save_inquiry_template(key=tpl_key, name=tpl_name, body=tpl_body, platform=tpl_platform, category=tpl_category)
        st.success("저장했습니다.") if r.get("ok") else st.error(r.get("error"))
        if r.get("ok"):
            st.rerun()

with inv_tab:
    st.caption("안전재고 이하가 연속 2회 확인될 때만 외부 품절 처리하고, 시스템이 직접 품절시킨 상품만 재입고 후 자동 판매재개합니다.")
    if data["inventory_states"]:
        st.dataframe([
            {
                "상품ID": x["product_id"], "관측재고": x["stock"], "저재고 확인": x["low_confirms"],
                "재입고 확인": x["restock_confirms"], "자동품절됨": x["auto_sold_out"],
                "마지막 동작": x["last_action"], "오류": x["last_error"], "확인시각": x["last_checked_at"],
            }
            for x in data["inventory_states"]
        ], use_container_width=True, hide_index=True)
    else:
        st.info("재고 자동화 실행 이력이 없습니다. 통합 판매 운영센터에서 상품별 안전재고 정책을 먼저 설정하세요.")
    st.info("재고 미확인(None)은 절대 0으로 간주하지 않습니다. 일시적인 공급처 API 장애로 전체 품절되는 것을 막습니다.")

with settle_tab:
    st.caption("쿠팡/스마트스토어 공식 정산 API를 수집하고 주문품목 손익원장과 매칭합니다.")
    if data["settlements"]:
        st.dataframe(data["settlements"], use_container_width=True, hide_index=True)
        total_revenue = sum(int(x.get("revenue") or 0) for x in data["settlements"])
        total_fee = sum(int(x.get("fee") or 0) for x in data["settlements"])
        total_settle = sum(int(x.get("settlement") or 0) for x in data["settlements"])
        a, b, c = st.columns(3)
        a.metric("수집 매출", f"{total_revenue:,}원")
        b.metric("수수료", f"{total_fee:,}원")
        c.metric("정산액", f"{total_settle:,}원")
    else:
        st.info("수집된 판매채널 정산 데이터가 없습니다.")

with bulk_tab:
    st.caption("product_id 또는 SKU 기준으로 수정하며, 신규 행은 SKU를 기준으로 생성합니다. 행별 오류는 다른 행의 처리를 중단시키지 않습니다.")
    template_bytes = build_bulk_product_template_xlsx(limit=5000)
    st.download_button(
        "현재 상품 포함 XLSX 템플릿 다운로드",
        data=template_bytes,
        file_name="autoseller_products_bulk.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    uploaded = st.file_uploader("수정/등록 XLSX 업로드", type=["xlsx"], key="bulk_product_xlsx")
    allow_create = st.checkbox("XLSX의 신규 SKU 생성 허용", value=True, key="bulk_allow_create")
    st.warning("실행하면 로컬 상품 마스터가 변경됩니다. 외부 마켓 상품을 즉시 수정하지는 않습니다.")
    if uploaded and st.button("XLSX 대량 적용", type="primary", key="bulk_apply"):
        try:
            result = apply_bulk_product_xlsx(uploaded.getvalue(), allow_create=allow_create)
            st.success(f"신규 {result['created']} / 수정 {result['updated']} / 건너뜀 {result['skipped']}")
            if result["errors"]:
                st.error(f"행 오류 {len(result['errors'])}건")
                st.dataframe(result["errors"], use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"XLSX 처리 실패: {type(exc).__name__}: {exc}")

with clone_tab:
    st.caption("원본 마켓 상품을 로컬 검토 상품으로 가져온 뒤 대상 마켓의 정상 승인 흐름으로 넘깁니다. 즉시 외부 등록하지 않습니다.")
    c1, c2 = st.columns(2)
    source_platform = c1.selectbox("원본 마켓", ["coupang", "smartstore"], key="clone_source")
    target_platform = c2.selectbox("대상 마켓", ["smartstore", "coupang"], key="clone_target")
    external_id = st.text_input("원본 상품 ID", key="clone_external_id")
    override = st.number_input("대상 판매가 재지정 (0=원본 판매가)", min_value=0, step=100, value=0, key="clone_price")
    if st.button("가져오기 + 대상마켓 등록 승인요청 생성", type="primary", key="clone_stage"):
        r = stage_marketplace_clone(
            source_platform,
            external_id,
            target_platform,
            sell_price_override=int(override) if override else None,
            actor="seller",
        )
        if r.get("ok"):
            st.success(f"로컬 상품 {r['sku']} 생성/확인 후 {target_platform} 등록 승인요청을 만들었습니다.")
            st.warning(r.get("warning", ""))
            st.json(r.get("approval") or {})
        else:
            st.error(r.get("error") or (r.get("approval") or {}).get("error") or "마켓 복제 준비 실패")

with sched_tab:
    st.caption("DB에 저장된 설정이 스케줄러의 실제 실행 주기가 됩니다. 최소 주기는 1분입니다.")
    rules = data["scheduler_rules"]
    if rules:
        st.dataframe(rules, use_container_width=True, hide_index=True)
        selected_rule = st.selectbox("수정할 작업", [x["task_type"] for x in rules], key="scheduler_rule_select")
        current = next(x for x in rules if x["task_type"] == selected_rule)
        s1, s2, s3 = st.columns(3)
        enabled = s1.checkbox("활성화", value=bool(current["enabled"]), key=f"sch_enabled_{selected_rule}")
        interval = s2.number_input("실행 간격(분)", min_value=1, max_value=10080, value=max(1, int(current["interval_minutes"])), key=f"sch_interval_{selected_rule}")
        queue_name = s3.selectbox("큐", ["sync", "automation"], index=0 if current["queue"] == "sync" else 1, key=f"sch_queue_{selected_rule}")
        payload_text = st.text_area("Payload JSON", value=json.dumps(current.get("payload") or {}, ensure_ascii=False, indent=2), key=f"sch_payload_{selected_rule}")
        if st.button("스케줄 저장", type="primary", key=f"sch_save_{selected_rule}"):
            try:
                payload = json.loads(payload_text or "{}")
                if not isinstance(payload, dict):
                    raise ValueError("Payload는 JSON 객체여야 합니다.")
                r = save_scheduler_rule(
                    selected_rule,
                    int(interval),
                    enabled=enabled,
                    queue_name=queue_name,
                    payload=payload,
                    description=str(current.get("description") or ""),
                )
                st.success("스케줄을 저장했습니다.") if r.get("ok") else st.error(r.get("error"))
                if r.get("ok"):
                    st.rerun()
            except Exception as exc:
                st.error(f"스케줄 저장 실패: {exc}")

with payment_tab:
    st.caption("카드사 앱 인증이 필요한 공급처는 결제 세션을 awaiting_user로 유지하고, 카드 승인 완료가 공급처에서 확인될 때만 발주완료로 전환합니다.")
    drivers = list_supplier_driver_status()
    st.markdown("#### 공급처 주문 드라이버")
    if drivers:
        st.dataframe(drivers, use_container_width=True, hide_index=True)
    else:
        st.warning("현재 런타임에 등록된 검증 공급처 주문 드라이버가 없습니다. 결제 세션을 실제 생성하려면 공급처별 검증 드라이버가 필요합니다.")
    st.markdown("#### 결제 세션")
    if payments:
        st.dataframe([
            {
                "ID": x["id"], "Fulfillment": x["fulfillment_id"], "공급처": x["supplier"],
                "방식": x["mode"], "상태": x["status"], "예상금액": x["expected_amount_krw"],
                "실제금액": x["actual_amount_krw"], "사용자승인": x["user_action_required"],
                "오류": x["error"], "수정": x["updated_at"],
            }
            for x in payments
        ], use_container_width=True, hide_index=True)
        actionable = [x for x in payments if x["user_action_required"] and x["payment_url"]]
        if actionable:
            labels = {f"결제 #{x['id']} · {x['supplier']} · {x['expected_amount_krw']:,}원": x for x in actionable}
            selected_payment = labels[st.selectbox("승인이 필요한 결제", list(labels), key="payment_select")]
            st.link_button("공급처 결제화면 열기", selected_payment["payment_url"], use_container_width=True)
            st.info("결제화면에서 카드 결제를 진행하고 휴대폰 카드사 앱에서 본인승인을 완료하세요. AutoSellerAI는 payment_sync로 완료 여부를 확인합니다.")
    else:
        st.info("생성된 결제 세션이 없습니다.")

st.divider()
st.caption("외부 API 쓰기와 실제 결제는 idempotency/승인/상태검증 계층을 유지합니다. 카드번호·CVC·카드 비밀번호는 AutoSellerAI에 저장하지 않습니다.")
