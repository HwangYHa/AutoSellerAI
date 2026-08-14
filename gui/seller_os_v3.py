"""Seller OS v3 — one operating workspace.

The UI contains no marketplace/supplier mutation logic and no direct ORM queries.
It calls the Seller OS application layer only.
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.os.approvals import decide_approval
from app.os.bridge import migrate_legacy_to_os
from app.os.connections import get_connection_summary
from app.os.dashboard import get_dashboard, list_orders, list_products
from app.os.operations import (
    approve_fulfillment_state,
    execute_listing_publish,
    request_listing_publish,
    request_order_fulfillment,
)
from app.os.queries import (
    get_operations_summary,
    get_order_detail,
    get_product_detail,
    get_profit_summary,
)
from app.os.schema import ensure_os_schema, get_os_health
from app.os.tasks import enqueue_task


_STATUS_KO = {
    "draft": "초안",
    "review": "검토",
    "ready": "판매 준비",
    "active": "판매중",
    "paused": "중지",
    "archived": "보관",
    "new": "신규",
    "exception": "예외",
    "ready_to_fulfill": "발주 준비",
    "fulfilling": "발주/배송 처리",
    "shipped": "배송중",
    "completed": "완료",
    "cancelled": "취소",
    "pending": "대기",
    "pending_approval": "승인 대기",
    "approved": "승인됨",
    "ordered": "발주됨",
    "failed": "실패",
    "succeeded": "성공",
    "queued": "대기",
    "running": "실행중",
    "settled": "정산 확정",
    "provisional": "정산 잠정",
    "estimated": "예상",
}


def _status(value: str) -> str:
    return _STATUS_KO.get(str(value), str(value))


def _krw(value: int | float | None) -> str:
    return f"{int(value or 0):,}원"


def _fmt_dt(value) -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        return value.replace("T", " ")[:16]
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


def _bootstrap() -> None:
    ensure_os_schema()
    # Legacy data migration is local/read-only with respect to external systems.
    # Run once per Streamlit browser session; later sync tasks call it again.
    if not st.session_state.get("seller_os_v3_bridge_done"):
        try:
            st.session_state["seller_os_v3_bridge_result"] = migrate_legacy_to_os()
        except Exception as exc:
            st.session_state["seller_os_v3_bridge_error"] = str(exc)
        st.session_state["seller_os_v3_bridge_done"] = True


def _hero() -> None:
    st.markdown(
        """
        <style>
          .block-container{max-width:1320px;padding-top:1.2rem;padding-bottom:5rem}
          .os-hero{padding:24px 28px;border-radius:18px;background:linear-gradient(135deg,#0f172a,#1e293b 58%,#312e81);color:white;margin-bottom:14px}
          .os-hero h1{font-size:28px;margin:0;font-weight:850}.os-hero p{margin:7px 0 0;color:#cbd5e1}
          [data-testid="stMetric"]{background:#fff;border:1px solid #e2e8f0;padding:12px;border-radius:12px}
          .small-muted{color:#64748b;font-size:.88rem}
        </style>
        <div class="os-hero">
          <h1>⚡ Seller OS</h1>
          <p>반복 작업은 자동화하고, 여기서는 승인 · 예외처리 · 전략결정만 합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_work_queue() -> None:
    data = get_dashboard()
    metrics = data["metrics"]
    health = data["health"]
    work = data["work_queue"]

    a, b, c, d, e = st.columns(5)
    a.metric("상품", metrics["products"])
    b.metric("판매중", metrics["active_listings"])
    c.metric("처리중 주문", metrics["open_orders"])
    d.metric("실제 순이익", _krw(metrics["profit_krw"]))
    e.metric("내가 처리할 일", len(work))

    st.markdown("### 오늘 할 일")
    st.caption("자동화가 처리하지 못했거나, 실제 비용/외부 변경 때문에 사람의 판단이 필요한 항목만 표시합니다.")
    if not work:
        st.success("현재 직접 처리해야 할 업무가 없습니다.")
    else:
        for row in work:
            with st.container(border=True):
                left, middle, right = st.columns([1.1, 5.0, 2.0], vertical_alignment="center")
                badge = {
                    "approval": "승인",
                    "order_exception": "주문 예외",
                    "fulfillment_failed": "발주 실패",
                    "task_failed": "자동화 실패",
                }.get(row["kind"], row["kind"])
                left.markdown(f"**{badge}**")
                middle.markdown(f"**{row['title']}**")
                middle.caption(f"{row['detail']} · {_fmt_dt(row.get('created_at'))}")
                right.write(row["action"])

                if row["kind"] == "approval":
                    cols = st.columns([1, 1, 4])
                    if cols[0].button("승인", key=f"approve_{row['id']}", type="primary", use_container_width=True):
                        result = decide_approval(int(row["id"]), approve=True, actor="seller")
                        if not result.get("ok"):
                            st.error(result.get("error", "승인 실패"))
                        else:
                            # Approval is the explicit user gate. Marketplace publishing
                            # is executed immediately after that same deliberate approval.
                            if "실제 상품 등록" in row["title"]:
                                executed = execute_listing_publish(int(row["id"]), actor="seller")
                                if executed.get("ok"):
                                    st.success("승인한 상품 등록을 1회 실행했습니다.")
                                else:
                                    st.error(executed.get("error", "상품 등록 실행 실패"))
                            elif "실제 발주" in row["title"]:
                                moved = approve_fulfillment_state(int(row["id"]))
                                if moved.get("ok"):
                                    st.success("발주 승인 완료. 검증된 공급처 주문 드라이버가 연결될 때만 실제 실행됩니다.")
                                else:
                                    st.error(moved.get("error", "발주 승인 처리 실패"))
                            else:
                                st.success("승인했습니다.")
                            st.rerun()
                    if cols[1].button("거절", key=f"reject_{row['id']}", use_container_width=True):
                        result = decide_approval(int(row["id"]), approve=False, actor="seller")
                        if result.get("ok"):
                            st.success("거절했습니다.")
                            st.rerun()
                        st.error(result.get("error", "거절 실패"))

    if health["unlinked_order_items"]:
        st.warning(f"내부 Product/Variant에 연결되지 않은 주문 품목이 {health['unlinked_order_items']}건 있습니다. 주문 · 배송에서 확인하세요.")


def _render_products() -> None:
    st.markdown("### 상품")
    st.caption("공급처 Offer → 내부 Product/Variant → 판매채널 Listing을 한 상품 상세에서 함께 봅니다.")
    f1, f2 = st.columns([2, 1])
    keyword = f1.text_input("상품 검색", placeholder="상품명 · SKU · 브랜드", key="os_product_keyword")
    status = f2.selectbox(
        "상태",
        ["", "draft", "review", "ready", "active", "paused", "archived"],
        format_func=lambda x: "전체" if not x else _status(x),
        key="os_product_status",
    )
    rows = list_products(status=status, keyword=keyword, limit=300)
    st.caption(f"{len(rows)}개 표시")
    if not rows:
        st.info("조건에 맞는 상품이 없습니다. 새 상품 확보는 ‘통합 상품 소싱’에서 진행하세요.")
        return

    st.dataframe(
        [
            {
                "ID": x["id"], "SKU": x["sku"], "상품": x["name"], "브랜드": x["brand"],
                "상태": _status(x["status"]), "판매채널": x["channels"] or "-", "수정": _fmt_dt(x["updated_at"]),
            }
            for x in rows
        ],
        use_container_width=True,
        hide_index=True,
    )
    choices = {f"#{x['id']} · {x['name'][:70]}": x["id"] for x in rows}
    selected_label = st.selectbox("상품 상세", list(choices.keys()), key="os_product_select")
    detail = get_product_detail(choices[selected_label])
    if not detail:
        return

    with st.container(border=True):
        st.markdown(f"#### {detail['name']}")
        st.caption(f"{detail['sku']} · {_status(detail['status'])} · {detail['brand'] or '브랜드 없음'} · {detail['category'] or '카테고리 없음'}")
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("Variant", len(detail["variants"]))
        v2.metric("공급 Offer", len(detail["offers"]))
        v3.metric("Listing", len(detail["listings"]))
        active = sum(1 for x in detail["listings"] if x["status"] == "active")
        v4.metric("판매중 채널", active)

        tab_offer, tab_listing, tab_content = st.tabs(["공급처 · 옵션", "판매채널", "콘텐츠"])
        with tab_offer:
            if detail["variants"]:
                st.dataframe(detail["variants"], use_container_width=True, hide_index=True)
            if detail["offers"]:
                st.dataframe(
                    [
                        {
                            "공급처": x["supplier"], "상품ID": x["supplier_product_id"],
                            "공급가": x["supply_price_krw"], "배송비": x["shipping_fee_krw"],
                            "재고": x["stock_qty"], "MOQ": x["moq"], "리드타임": x["lead_time_days"],
                            "상태": x["status"], "동기화": _fmt_dt(x["last_synced_at"]),
                        }
                        for x in detail["offers"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.warning("연결된 공급처 Offer가 없습니다.")
        with tab_listing:
            if detail["listings"]:
                st.dataframe(
                    [
                        {
                            "채널": x["platform"], "상태": _status(x["status"]),
                            "판매가": x["sale_price_krw"], "외부상품ID": x["external_product_id"], "오류": x["error"],
                        }
                        for x in detail["listings"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("아직 판매채널에 등록되지 않았습니다.")
            if detail["status"] in {"ready", "active"}:
                c1, c2 = st.columns(2)
                if c1.button("쿠팡 등록 승인 요청", key=f"pub_cp_{detail['id']}", use_container_width=True):
                    r = request_listing_publish(detail["id"], "coupang", actor="seller")
                    if r.get("ok"):
                        st.success("‘오늘 할 일’에 실제 등록 승인 요청을 만들었습니다.")
                    else:
                        st.error(r.get("error", "요청 실패"))
                if c2.button("스마트스토어 등록 승인 요청", key=f"pub_ss_{detail['id']}", use_container_width=True):
                    r = request_listing_publish(detail["id"], "smartstore", actor="seller")
                    if r.get("ok"):
                        st.success("‘오늘 할 일’에 실제 등록 승인 요청을 만들었습니다.")
                    else:
                        st.error(r.get("error", "요청 실패"))
        with tab_content:
            content = detail["content"]
            images = content.get("images") or []
            details = content.get("detail_images") or []
            c1, c2, c3 = st.columns(3)
            c1.metric("대표 이미지", len(images))
            c2.metric("상세 이미지", len(details))
            c3.metric("상세 HTML", "있음" if content.get("detail_html") else "없음")
            st.caption("이미지 · SEO · 상세페이지 제작은 별도 데이터가 아니라 이 Product의 콘텐츠를 갱신합니다.")


def _render_orders() -> None:
    st.markdown("### 주문 · 배송")
    st.caption("판매채널 주문 한 건을 주문품목 → 공급처 Offer → 실제 발주 → 송장까지 끊김 없이 추적합니다.")
    a, b = st.columns([2, 1])
    status = a.selectbox(
        "주문 상태",
        ["", "new", "exception", "ready_to_fulfill", "fulfilling", "shipped", "completed", "cancelled"],
        format_func=lambda x: "전체" if not x else _status(x),
        key="os_order_status",
    )
    if b.button("신규 주문 동기화", type="primary", use_container_width=True):
        result = enqueue_task("order_sync", {"hours": 24}, queue_name="sync", dedupe_key="order_sync")
        if result.get("ok"):
            st.success(f"백그라운드 작업 #{result['task_id']} 시작")
        else:
            st.error(result.get("error", "작업 시작 실패"))

    rows = list_orders(status=status, limit=300)
    if not rows:
        st.info("수집된 주문이 없습니다.")
        return
    st.dataframe(
        [
            {
                "ID": x["id"], "채널": x["platform"], "주문번호": x["order_no"],
                "상태": _status(x["status"]), "수취인": x["receiver"], "품목": x["items"],
                "예외": x["exceptions"], "주문금액": x["amount_krw"], "주문시각": _fmt_dt(x["ordered_at"]),
            }
            for x in rows
        ],
        use_container_width=True,
        hide_index=True,
    )
    choices = {f"#{x['id']} · {x['platform']} · {x['order_no']}": x["id"] for x in rows}
    selected = st.selectbox("주문 상세", list(choices.keys()), key="os_order_select")
    detail = get_order_detail(choices[selected])
    if not detail:
        return

    with st.container(border=True):
        st.markdown(f"#### {detail['platform'].upper()} · {detail['order_no']}")
        st.caption(f"{_status(detail['status'])} · {detail['receiver_name']} · {_fmt_dt(detail['ordered_at'])}")
        st.write(f"배송지: {detail['shipping_address'] or '-'}")
        if detail["shipping_message"]:
            st.write(f"배송메모: {detail['shipping_message']}")

        for item in detail["items"]:
            with st.container(border=True):
                l, r = st.columns([5, 1.5])
                l.markdown(f"**{item['product_name'] or '상품 미확인'}**")
                l.caption(
                    f"수량 {item['quantity']} · {_krw(item['unit_sale_price_krw'])} · "
                    f"Product #{item['product_id'] or '-'} · Variant #{item['variant_id'] or '-'} · {_status(item['status'])}"
                )
                if item["exception_code"]:
                    r.error(item["exception_code"])
                else:
                    r.success(_status(item["status"]))

                fulfillment = item["fulfillment"]
                if fulfillment:
                    st.write(
                        f"공급처: {fulfillment['supplier_code'] or '-'} · "
                        f"발주번호: {fulfillment['supplier_order_id'] or '-'} · "
                        f"발주상태: {_status(fulfillment['status'])}"
                    )
                    if fulfillment["tracking_number"]:
                        st.write(f"송장: {fulfillment['delivery_company'] or '-'} {fulfillment['tracking_number']}")
                    if fulfillment["failure_message"]:
                        st.error(fulfillment["failure_message"])
                elif item["product_id"] and item["status"] in {"ready", "new"}:
                    if st.button("공급처 실제 발주 승인 요청", key=f"fulfill_{item['id']}", use_container_width=True):
                        result = request_order_fulfillment(item["id"], actor="seller")
                        if result.get("ok"):
                            st.success("‘오늘 할 일’에 발주 승인 요청을 만들었습니다.")
                        else:
                            st.error(result.get("error", "발주 요청 실패"))

                if item["settlement"]:
                    settlement = item["settlement"]
                    st.caption(
                        f"실제 손익 · 매출 {_krw(settlement['gross_revenue_krw'])} / "
                        f"공급가 {_krw(settlement['supply_cost_krw'])} / 순이익 {_krw(settlement['net_profit_krw'])}"
                    )


def _render_profit() -> None:
    st.markdown("### 수익")
    st.caption("판매가의 예상마진이 아니라 주문품목별 실제 비용과 정산값을 기준으로 봅니다.")
    data = get_profit_summary()
    s = data["summary"]
    a, b, c, d, e = st.columns(5)
    a.metric("매출", _krw(s["gross_revenue_krw"]))
    b.metric("공급가", _krw(s["supply_cost_krw"]))
    c.metric("플랫폼 수수료", _krw(s["platform_fee_krw"]))
    d.metric("순이익", _krw(s["net_profit_krw"]))
    e.metric("순이익률", f"{s['margin_pct']:.2f}%")

    st.markdown("#### 채널별")
    st.dataframe(
        [
            {"채널": x["platform"], "정산품목": x["orders"], "매출": x["revenue_krw"], "순이익": x["profit_krw"]}
            for x in data["by_platform"]
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("#### 최근 손익 원장")
    if data["recent"]:
        st.dataframe(data["recent"], use_container_width=True, hide_index=True)
    else:
        st.info("아직 정산 원장이 없습니다.")


def _render_settings() -> None:
    st.markdown("### 설정 · 자동화")
    st.caption("평소에 공급처별 화면을 돌아다니지 않습니다. 연결·작업큐·데이터 건강도·감사이력을 여기서 봅니다.")

    conn = get_connection_summary()
    st.markdown("#### 연결")
    st.dataframe(
        [
            {
                "구분": x["kind"], "서비스": x["name"], "상태": "설정됨" if x["configured"] else "확인 필요",
                "기능": ", ".join(x["capabilities"]),
            }
            for x in conn["rows"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### 안전 자동화")
    c1, c2, c3, c4 = st.columns(4)
    actions = [
        (c1, "카탈로그 동기화", "catalog_sync", {}, "catalog_sync"),
        (c2, "주문 동기화", "order_sync", {"hours": 24}, "order_sync"),
        (c3, "데이터 관계 복구", "data_reconcile", {"remote": True}, "data_reconcile"),
        (c4, "전체 이미지 복구", "image_repair", {"include_marketplaces": True}, "image_repair"),
    ]
    for col, label, task_type, payload, dedupe in actions:
        if col.button(label, use_container_width=True, key=f"task_{task_type}"):
            result = enqueue_task(task_type, payload, queue_name="sync", dedupe_key=dedupe)
            if result.get("ok"):
                st.success(f"작업 #{result['task_id']} 접수")
            else:
                st.error(result.get("error", "작업 큐 실패"))

    st.markdown("#### 데이터 건강도")
    health = get_os_health()
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("미연결 주문품목", health["unlinked_order_items"])
    h2.metric("미처리 Fulfillment", health["unfulfilled_order_items"])
    h3.metric("승인 대기", health["pending_approvals"])
    h4.metric("실패 작업", health["failed_tasks"] + health["failed_operations"])

    ops = get_operations_summary(limit=40)
    o1, o2, o3 = st.tabs(["백그라운드 작업", "위험 작업 실행이력", "감사 로그"])
    with o1:
        if ops["tasks"]:
            st.dataframe(ops["tasks"], use_container_width=True, hide_index=True)
        else:
            st.info("작업 이력이 없습니다.")
    with o2:
        if ops["operations"]:
            st.dataframe(ops["operations"], use_container_width=True, hide_index=True)
        else:
            st.info("실제 외부 변경 작업 이력이 없습니다.")
    with o3:
        if ops["audit"]:
            st.dataframe(ops["audit"], use_container_width=True, hide_index=True)
        else:
            st.info("감사 이력이 없습니다.")

    st.markdown("#### 안전 원칙")
    st.info(
        "재고 사입 PurchaseOrder/MOQ는 위탁판매 기본 업무에서 제외합니다. "
        "신규 상품등록·공급처 실제 발주·유료 생성·대량 변경은 Approval + Idempotency Gate를 통과해야 합니다."
    )


def render_seller_os_v3() -> None:
    _bootstrap()
    _hero()
    tab_work, tab_products, tab_orders, tab_profit, tab_settings = st.tabs(
        ["🎯 오늘 할 일", "📦 상품", "🚚 주문 · 배송", "💰 수익", "⚙️ 설정 · 자동화"]
    )
    with tab_work:
        _render_work_queue()
    with tab_products:
        _render_products()
    with tab_orders:
        _render_orders()
    with tab_profit:
        _render_profit()
    with tab_settings:
        _render_settings()
