"""쿠팡/스마트스토어 전체 상품 진단 → 비교 → 사용자 승인 → 선택/일괄 반영."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import streamlit as st

from app.config import get_settings
from app.db import Listing, Product, get_db, init_db
from app.seo.market_optimizer import MarketSeoOptimizer, SEO_WRITE_FIELDS
from app.seo.market_models import ensure_market_seo_schema
from app.platforms.coupang import reset_coupang_uploader
from app.platforms.smartstore import reset_smartstore_uploader
from gui.korean_runtime import apply_korean_patch

apply_korean_patch()
st.set_page_config(page_title="마켓 SEO 자동최적화 | 오토셀러 AI", page_icon="📈", layout="wide")
init_db()
ensure_market_seo_schema()

st.markdown("## 📈 마켓 SEO 자동최적화")
st.caption(
    "쿠팡 Wing·네이버 스마트스토어에 이미 판매 중인 상품을 실제 판매자 API에서 다시 읽어 "
    "상품명·태그·카테고리·속성·이미지·상세정보·판매상태·성과 신호를 진단합니다. "
    "검색 상위노출을 보장하는 기능이 아니라 검색 적합성과 상품정보 완성도를 개선하는 운영 도구입니다."
)
st.warning(
    "라이브 상품은 자동으로 바뀌지 않습니다. 카테고리·가격·배송·이미지·확인되지 않은 속성값은 항상 잠금 상태이며, "
    "상품명/태그/상세/확인된 브랜드도 최종 적용 전에 사용자가 직접 선택·승인해야 합니다."
)


def _optimizer() -> MarketSeoOptimizer:
    # 환경설정 변경 뒤에도 새 자격증명을 사용하도록 세션 단위로 재생성한다.
    if "market_seo_optimizer" not in st.session_state:
        reset_coupang_uploader(); reset_smartstore_uploader()
        st.session_state["market_seo_optimizer"] = MarketSeoOptimizer()
    return st.session_state["market_seo_optimizer"]


def _connected_products() -> list[dict]:
    with get_db() as db:
        rows = (
            db.query(Listing, Product)
            .join(Product, Product.id == Listing.product_id)
            .filter(Listing.status == "success")
            .filter(Listing.platform.in_(["coupang", "smartstore"]))
            .order_by(Listing.platform, Product.name)
            .all()
        )
        return [{
            "선택": False,
            "상품ID": p.id,
            "플랫폼": "쿠팡" if l.platform == "coupang" else "스마트스토어",
            "platform": l.platform,
            "판매채널 상품번호": l.platform_id,
            "상품명": p.name,
            "판매가": int(p.sell_price or 0),
            "카테고리": p.category,
            "브랜드": p.brand,
        } for l, p in rows]


def _fmt(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if value is None:
        return ""
    text = str(value)
    return text if len(text) <= 900 else text[:900] + "\n…"


def _safe_field_default(audit: dict, field: str) -> bool:
    current = audit.get("current") or {}; proposed = audit.get("proposed") or {}
    if field == "detail":
        changed = bool(proposed.get("detail_html")) and proposed.get("detail_html") != current.get("detail_html")
    else:
        changed = proposed.get(field) not in (None, "", []) and proposed.get(field) != current.get(field)
    if field == "title" and audit.get("sales_protected"):
        return False
    return bool(changed)


settings = get_settings()
left, right = st.columns(2)
with left:
    cp_ready = bool((settings.coupang_access_key or "").strip() and (settings.coupang_secret_key or "").strip() and (settings.coupang_vendor_id or "").strip())
    st.metric("쿠팡 Wing API", "연결정보 있음" if cp_ready else "설정 필요")
with right:
    nv_ready = bool((settings.naver_client_id or "").strip() and (settings.naver_client_secret or "").strip())
    st.metric("네이버 Commerce API", "연결정보 있음" if nv_ready else "설정 필요")

with st.expander("🔌 이 화면에서 활용하는 공개 API 범위 / 제한사항", expanded=False):
    caps = MarketSeoOptimizer.capabilities()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**쿠팡**")
        st.write("조회: " + " · ".join(caps["coupang"]["read"]))
        st.write("승인 후 수정: " + " · ".join(caps["coupang"]["write"]))
        st.write("🔒 자동변경 금지: " + " · ".join(caps["coupang"]["locked"]))
    with c2:
        st.markdown("**스마트스토어**")
        st.write("조회: " + " · ".join(caps["smartstore"]["read"]))
        st.write("승인 후 수정: " + " · ".join(caps["smartstore"]["write"]))
        st.write("🔒 자동변경 금지: " + " · ".join(caps["smartstore"]["locked"]))
    st.info("공개 판매자 API에서 직접 제공되지 않는 값: " + " · ".join(caps["not_public"]) + ". AutoSellerAI에 수집된 ProductPerformance가 있을 때만 노출·클릭 신호를 함께 사용합니다.")

sync_tab, audit_tab, compare_tab, history_tab = st.tabs([
    "① 전체상품 가져오기", "② 자동/선택 진단", "③ 비교·승인·적용", "④ 진단기록/API 근거"
])

with sync_tab:
    st.markdown("### 판매채널 전체 상품 역동기화")
    st.write("Wing/스마트스토어에서 직접 올렸거나 수정한 상품까지 AutoSellerAI로 가져옵니다. 이 단계는 **읽기 전용**입니다.")
    s1, s2, s3 = st.columns(3)
    sync_cp = s1.button("🟠 쿠팡 전체 가져오기", use_container_width=True, disabled=not cp_ready)
    sync_nv = s2.button("🟢 스마트스토어 전체 가져오기", use_container_width=True, disabled=not nv_ready)
    sync_all = s3.button("🔄 연결된 채널 모두 가져오기", type="primary", use_container_width=True, disabled=not (cp_ready or nv_ready))
    selected_sync = []
    if sync_cp or sync_all:
        if cp_ready: selected_sync.append("coupang")
    if sync_nv or sync_all:
        if nv_ready: selected_sync.append("smartstore")
    if selected_sync:
        try:
            with st.spinner("판매채널 상품 목록과 상세정보를 가져오는 중입니다. 상품 수에 따라 시간이 걸릴 수 있습니다..."):
                result = _optimizer().sync_catalog(selected_sync)
            for platform, item in result.items():
                label = "쿠팡" if platform == "coupang" else "스마트스토어"
                if item.get("ok"):
                    st.success(f"{label}: 발견 {item.get('total_found', 0)} · 신규 {item.get('created', 0)} · 연결 {item.get('linked', 0)} · 갱신 {item.get('updated', 0)}")
                else:
                    st.error(f"{label} 동기화 실패: {item.get('error')}")
            st.session_state["market_seo_optimizer"] = MarketSeoOptimizer()
        except Exception as exc:
            st.error(f"동기화 실행 실패: {exc}")

    rows = _connected_products()
    m1, m2, m3 = st.columns(3)
    m1.metric("연결 상품", len(rows))
    m2.metric("쿠팡", sum(1 for x in rows if x["platform"] == "coupang"))
    m3.metric("스마트스토어", sum(1 for x in rows if x["platform"] == "smartstore"))
    if rows:
        st.dataframe(pd.DataFrame(rows).drop(columns=["선택", "platform"]), use_container_width=True, hide_index=True, height=460)
    else:
        st.info("연결된 판매채널 상품이 없습니다. 먼저 전체 가져오기를 실행하세요.")

with audit_tab:
    st.markdown("### 자동 진단 범위 선택")
    rows = _connected_products()
    platforms = st.multiselect(
        "진단 채널", ["coupang", "smartstore"], default=[x for x, ok in (("coupang", cp_ready), ("smartstore", nv_ready)) if ok],
        format_func=lambda x: "쿠팡" if x == "coupang" else "스마트스토어",
    )
    deep = st.checkbox(
        "정밀 API 진단 (카테고리 메타·태그·검수·카탈로그/상태이력까지 조회)", value=True,
        help="상품 상세만 보는 빠른 진단보다 API 호출 수가 많습니다. 카테고리 메타는 같은 카테고리끼리 캐시합니다.",
    )
    scope = st.radio("진단 방식", ["전체 상품 자동 진단", "선택 상품만 진단"], horizontal=True)
    filtered_targets = [x for x in rows if x["platform"] in platforms]
    selected_ids: list[int] | None = None
    if scope == "선택 상품만 진단":
        query = st.text_input("상품명/상품번호 검색", placeholder="예: 차량용 청소기")
        display = filtered_targets
        if query.strip():
            q = query.strip().casefold()
            display = [x for x in display if q in x["상품명"].casefold() or q in str(x["판매채널 상품번호"]).casefold()]
        editor = st.data_editor(
            pd.DataFrame(display)[["선택", "상품ID", "플랫폼", "판매채널 상품번호", "상품명", "판매가", "카테고리"]] if display else pd.DataFrame(),
            use_container_width=True, hide_index=True, height=430,
            disabled=["상품ID", "플랫폼", "판매채널 상품번호", "상품명", "판매가", "카테고리"],
            column_config={"선택": st.column_config.CheckboxColumn("선택", default=False)},
            key="seo_target_editor",
        )
        if not editor.empty:
            selected_ids = [int(x) for x in editor.loc[editor["선택"] == True, "상품ID"].tolist()]  # noqa: E712
        st.caption(f"선택 {len(selected_ids or [])}개 / 표시 {len(display)}개")
    else:
        st.info(f"현재 선택한 채널의 연결 상품 **{len(filtered_targets)}개**를 순차 진단합니다. 라이브 상품 수정은 아직 하지 않습니다.")

    run_audit = st.button(
        "🚀 전체 자동 진단 시작" if scope.startswith("전체") else "🔎 선택 상품 진단 시작",
        type="primary", use_container_width=True,
        disabled=not platforms or not filtered_targets or (scope.startswith("선택") and not selected_ids),
    )
    if run_audit:
        try:
            progress = st.progress(0, text="원격 상품정보와 SEO 조건을 분석할 준비 중...")
            with st.spinner("정밀 진단 중입니다. 외부 API 호출 수에 따라 시간이 걸릴 수 있습니다..."):
                opt = _optimizer()
                if scope.startswith("전체"):
                    result = opt.audit_all(platforms, deep=deep)
                else:
                    result = opt.audit_selected(platforms=platforms, product_ids=selected_ids, deep=deep)
            progress.progress(100, text="진단 완료")
            st.session_state["market_seo_latest"] = result
            ok_count = sum(1 for x in result if x.get("quality_score", 0) > 0)
            st.success(f"진단 완료: {len(result)}개 처리 · 정상 분석 {ok_count}개. 이제 ‘③ 비교·승인·적용’에서 수정안을 검토하세요.")
        except Exception as exc:
            st.error(f"진단 실패: {exc}")

    audits = st.session_state.get("market_seo_latest") or MarketSeoOptimizer.latest_audits(limit=2000)
    if audits:
        st.markdown("### 자동 분류 요약")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("S급 즉시 검토", sum(1 for x in audits if x.get("priority_grade") == "S"))
        q2.metric("A급", sum(1 for x in audits if x.get("priority_grade") == "A"))
        q3.metric("치명 문제 상품", sum(1 for x in audits if int(x.get("critical_count") or 0) > 0))
        q4.metric("판매이력 보호", sum(1 for x in audits if x.get("sales_protected")))
        summary_df = pd.DataFrame([{
            "플랫폼": "쿠팡" if x["platform"] == "coupang" else "스마트스토어",
            "상품ID": x["product_id"], "상품명": x["product_name"],
            "현재점수": x["quality_score"], "예상개선점수": x["proposed_score"],
            "기회점수": x["opportunity_score"], "등급": x["priority_grade"],
            "자동분류": x.get("classification_label") or x.get("classification"),
            "치명": x.get("critical_count", 0), "경고": x.get("warning_count", 0),
            "30일 주문": x.get("recent_orders", 0), "판매보호": "🔒" if x.get("sales_protected") else "",
        } for x in audits])
        st.dataframe(summary_df, use_container_width=True, hide_index=True, height=480)

with compare_tab:
    audits = st.session_state.get("market_seo_latest") or MarketSeoOptimizer.latest_audits(limit=2000)
    if not audits:
        st.info("먼저 ‘② 자동/선택 진단’에서 상품을 진단하세요.")
    else:
        st.markdown("### 문제상품 필터 · 선택")
        f1, f2, f3, f4 = st.columns(4)
        platform_filter = f1.selectbox("플랫폼", ["전체", "쿠팡", "스마트스토어"])
        grade_filter = f2.multiselect("우선등급", ["S", "A", "B", "C"], default=["S", "A", "B", "C"])
        problem_only = f3.checkbox("문제 있는 상품만", value=True)
        protect_only = f4.checkbox("판매이력 상품만", value=False)
        query = st.text_input("결과 내 상품명/상품ID 검색", key="seo_result_query")
        visible = []
        for x in audits:
            if platform_filter == "쿠팡" and x["platform"] != "coupang": continue
            if platform_filter == "스마트스토어" and x["platform"] != "smartstore": continue
            if x.get("priority_grade") not in grade_filter: continue
            if problem_only and int(x.get("issue_count") or 0) <= 0: continue
            if protect_only and not x.get("sales_protected"): continue
            if query.strip() and query.casefold() not in f"{x.get('product_id')} {x.get('product_name')}".casefold(): continue
            visible.append(x)

        select_df = pd.DataFrame([{
            "선택": False, "진단ID": x["id"], "플랫폼": "쿠팡" if x["platform"] == "coupang" else "스마트스토어",
            "상품ID": x["product_id"], "상품명": x["product_name"], "점수": x["quality_score"],
            "예상": x["proposed_score"], "등급": x["priority_grade"], "치명": x["critical_count"],
            "경고": x["warning_count"], "30일주문": x["recent_orders"], "보호": "🔒" if x["sales_protected"] else "",
        } for x in visible])
        edited = st.data_editor(
            select_df, use_container_width=True, hide_index=True, height=420,
            disabled=[c for c in select_df.columns if c != "선택"] if not select_df.empty else [],
            column_config={"선택": st.column_config.CheckboxColumn("선택", default=False)}, key="seo_audit_selector",
        ) if not select_df.empty else pd.DataFrame()
        selected_audit_ids = [int(x) for x in edited.loc[edited["선택"] == True, "진단ID"].tolist()] if not edited.empty else []  # noqa: E712

        st.divider()
        st.markdown("### 한 상품 정밀 비교")
        options = {int(x["id"]): x for x in visible if x.get("id")}
        if options:
            selected_detail_id = st.selectbox(
                "비교할 상품", list(options.keys()),
                format_func=lambda aid: f"[{('쿠팡' if options[aid]['platform']=='coupang' else '스마트스토어')}] #{options[aid]['product_id']} {options[aid]['product_name']}",
            )
            audit = options[selected_detail_id]
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("현재 완성도", f"{audit['quality_score']:.1f}")
            a2.metric("승인안 예상", f"{audit['proposed_score']:.1f}", f"+{max(0, audit['proposed_score']-audit['quality_score']):.1f}")
            a3.metric("우선순위", audit["priority_grade"])
            a4.metric("30일 주문", audit["recent_orders"])
            if audit.get("sales_protected"):
                st.warning("이 상품은 최근 판매이력이 있습니다. 제목 변경은 기본 선택 해제되며 별도 보호 해제 확인이 필요합니다.")

            issue_rows = [{
                "심각도": "🔴" if i["severity"] == "critical" else "🟠" if i["severity"] == "warning" else "🔵",
                "영역": i["area"], "문제": i["title"], "진단근거": i["reason"],
                "자동반영": "가능" if i.get("auto_applicable") and not i.get("locked") else "🔒 추천/확인만",
            } for i in audit.get("issues", [])]
            st.dataframe(issue_rows, use_container_width=True, hide_index=True)

            current = audit.get("current") or {}; proposed = audit.get("proposed") or {}
            field_specs = [
                ("title", "상품명", current.get("title"), proposed.get("title"), True),
                ("tags", "검색어/태그", current.get("tags"), proposed.get("tags"), True),
                ("brand", "브랜드", current.get("brand"), proposed.get("brand"), True),
                ("detail", "상세정보", current.get("detail_html") or current.get("detail"), proposed.get("detail_html"), True),
                ("category", "카테고리", current.get("category"), proposed.get("category"), False),
                ("price", "가격", current.get("sale_price") or audit.get("current", {}).get("price"), proposed.get("price"), False),
                ("shipping", "배송", current.get("delivery") or {"type": current.get("delivery_charge_type"), "charge": current.get("delivery_charge")}, proposed.get("shipping"), False),
                ("attributes", "카테고리/검색 속성", current.get("attributes"), audit.get("evidence", {}).get("missing_required_attributes"), False),
                ("images", "대표/추가 이미지", current.get("image_count"), "이미지 제작 화면에서 별도 검토", False),
            ]
            st.markdown("#### 기존 정보 ↔ 수정안")
            compare_rows = []
            for key, label, old, new, writable in field_specs:
                compare_rows.append({"항목": label, "현재": _fmt(old), "수정안/진단": _fmt(new), "라이브 자동반영": "사용자 선택 가능" if writable else "🔒 자동변경 금지"})
            st.dataframe(compare_rows, use_container_width=True, hide_index=True, height=460)

            st.markdown("#### 이 상품에서 실제 적용할 필드")
            c1, c2, c3, c4 = st.columns(4)
            field_checks = {
                "title": c1.checkbox("상품명", value=_safe_field_default(audit, "title"), key=f"field_title_{selected_detail_id}"),
                "tags": c2.checkbox("검색어/태그", value=_safe_field_default(audit, "tags"), key=f"field_tags_{selected_detail_id}"),
                "brand": c3.checkbox("확인된 브랜드", value=_safe_field_default(audit, "brand"), key=f"field_brand_{selected_detail_id}"),
                "detail": c4.checkbox("상세정보", value=_safe_field_default(audit, "detail"), key=f"field_detail_{selected_detail_id}"),
            }
            chosen_fields = {k for k, v in field_checks.items() if v}
            st.caption("카테고리·가격·배송·이미지·미확인 속성값은 이 화면에서 체크할 수 없도록 설계되어 있습니다.")
            protect_confirm = True
            if audit.get("sales_protected") and "title" in chosen_fields:
                protect_confirm = st.checkbox("🔓 판매이력이 있지만 이 상품의 제목 변경을 직접 승인합니다.", value=False, key=f"protect_{selected_detail_id}")
            final_one = st.checkbox("위 기존값/수정안을 비교했으며 선택 필드의 라이브 반영을 최종 승인합니다.", value=False, key=f"confirm_{selected_detail_id}")
            if st.button("✅ 이 상품 선택 필드 적용", type="primary", use_container_width=True, disabled=not chosen_fields or not final_one or not protect_confirm):
                opt = _optimizer()
                approved = opt.approve_fields(selected_detail_id, chosen_fields)
                if not approved.get("ok"):
                    st.error(approved.get("error"))
                else:
                    with st.spinner("최신 원격 상품 전문을 다시 읽은 뒤 승인 필드만 반영하는 중..."):
                        result = opt.apply_audit(selected_detail_id, chosen_fields, confirm_sales_protected=protect_confirm)
                    if result.get("ok"):
                        st.success("라이브 상품 반영 완료. 옵션/가격/카테고리/배송 등 선택하지 않은 필드는 기존 원격 값을 유지했습니다.")
                        st.session_state.pop("market_seo_latest", None)
                    else:
                        st.error(f"반영 실패: {result.get('error')}")

            st.markdown("#### API 근거/진단 제한")
            st.json(audit.get("data_sources") or {})
            if audit.get("limitations"):
                for limitation in audit["limitations"]:
                    st.info(limitation)
            with st.expander("진단 증거 상세 JSON"):
                st.json(audit.get("evidence") or {})

        st.divider()
        st.markdown("### 선택 상품 / 필터 전체 일괄 승인 적용")
        st.write("아래 선택은 **모든 필드를 강제로 바꾸는 기능이 아닙니다.** 지정한 SEO 필드만 각 상품 수정안에 값이 있을 때 순차 반영합니다.")
        bulk_fields = set(st.multiselect(
            "일괄 반영할 필드", ["title", "tags", "brand", "detail"], default=["tags"],
            format_func=lambda x: {"title":"상품명", "tags":"검색어/태그", "brand":"확인된 브랜드", "detail":"상세정보"}[x],
        ))
        mode = st.radio("일괄 대상", ["위 표에서 체크한 상품", "현재 필터 결과 전체"], horizontal=True)
        bulk_ids = selected_audit_ids if mode.startswith("위 표") else [int(x["id"]) for x in visible if x.get("id")]
        protected_title_count = sum(1 for x in visible if int(x.get("id") or 0) in bulk_ids and x.get("sales_protected")) if "title" in bulk_fields else 0
        if protected_title_count:
            st.warning(f"제목 일괄 변경 대상 중 판매이력 보호 상품이 {protected_title_count}개 있습니다.")
            bulk_protect = st.checkbox("🔓 판매이력 보호 상품의 제목 변경도 일괄 최종 승인", value=False)
        else:
            bulk_protect = True
        bulk_confirm = st.checkbox(f"대상 {len(bulk_ids)}개 · 필드 {', '.join(sorted(bulk_fields)) or '없음'}의 라이브 일괄 반영을 최종 승인합니다.", value=False, key="bulk_final_confirm")
        if st.button("🚀 승인 필드 일괄 적용", use_container_width=True, disabled=not bulk_ids or not bulk_fields or not bulk_confirm or not bulk_protect):
            selections = {aid: bulk_fields for aid in bulk_ids}
            opt = _optimizer()
            with st.spinner("상품마다 최신 원격 전문을 다시 조회하고 승인 필드만 순차 적용하는 중..."):
                for aid in bulk_ids:
                    opt.approve_fields(aid, bulk_fields)
                result = opt.apply_many(selections, confirm_sales_protected=bulk_protect)
            if result.get("failed"):
                st.warning(f"일괄 적용 완료: 성공 {result.get('success')} / 실패 {result.get('failed')}")
                with st.expander("실패 상세"):
                    st.json([x for x in result.get("results", []) if not x.get("ok")])
            else:
                st.success(f"일괄 적용 완료: {result.get('success')}개 성공")
            st.session_state.pop("market_seo_latest", None)

with history_tab:
    st.markdown("### 최근 진단 기록")
    history = MarketSeoOptimizer.latest_audits(limit=2000)
    if history:
        st.dataframe(pd.DataFrame([{
            "진단ID": x["id"], "플랫폼": x["platform"], "상품ID": x["product_id"], "상품명": x["product_name"],
            "현재점수": x["quality_score"], "예상점수": x["proposed_score"], "등급": x["priority_grade"],
            "분류": x["classification_label"], "문제": x["issue_count"], "상태": x["status"],
            "진단시각": x["analyzed_at"], "적용시각": x["applied_at"], "오류": x["error"],
        } for x in history]), use_container_width=True, hide_index=True, height=500)
    else:
        st.info("저장된 진단 기록이 없습니다.")
    st.markdown("### 운영 원칙")
    st.write(
        "진단은 공개 판매자 API와 AutoSellerAI 내부 성과 데이터만 사용합니다. 검색 순위나 내부 알고리즘 점수를 추정값처럼 표시하지 않습니다. "
        "상품을 변경할 때는 매번 플랫폼에서 최신 전문을 다시 읽고 선택한 필드만 변경하므로 옵션·재고·가격 등의 다른 필드를 덮어쓰지 않도록 보호합니다."
    )
    st.page_link("pages/05_판매채널_상품동기화.py", label="🔄 기존 판매채널 동기화 화면", use_container_width=True)
    st.page_link("pages/25_AI_상세페이지_제작.py", label="🖼️ 썸네일/상세 이미지 제작 화면", use_container_width=True)

st.caption(f"화면 기준 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · 자동 상위노출 보장 없음 · 사용자 승인 없는 라이브 변경 없음")
