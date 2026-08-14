"""Seller OS v3 — one operating workspace.

UI rule: no ORM queries, supplier mutations or marketplace mutations.  The browser
only submits decisions and safe task requests to the Seller OS application layer.
"""
from __future__ import annotations

import streamlit as st

from app.os.approvals import decide_approval
from app.os.bridge import migrate_legacy_to_os
from app.os.connections import get_connection_summary
from app.os.dashboard import get_dashboard, list_orders, list_products
from app.os.operations import approve_fulfillment_state, request_listing_publish, request_order_fulfillment
from app.os.queries import get_operations_summary, get_order_detail, get_product_detail, get_profit_summary
from app.os.schema import ensure_os_schema, get_os_health
from app.os.tasks import enqueue_task


_STATUS_KO = {
    "draft": "초안", "review": "검토", "ready": "판매 준비", "active": "판매중",
    "paused": "중지", "archived": "보관", "new": "신규", "exception": "예외",
    "ready_to_fulfill": "발주 준비", "fulfilling": "발주/배송 처리", "shipped": "배송중",
    "completed": "완료", "cancelled": "취소", "pending": "대기", "pending_approval": "승인 대기",
    "approved": "승인됨", "ordered": "발주됨", "failed": "실패", "succeeded": "성공",
    "queued": "대기", "running": "실행중", "settled": "정산 확정", "provisional": "정산 잠정",
    "estimated": "예상",
}


def _status(value: str) -> str:
    return _STATUS_KO.get(str(value), str(value))


def _krw(value) -> str:
    return f"{int(value or 0):,}원"


def _dt(value) -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        return value.replace("T", " ")[:16]
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


def _external_id(value: str) -> str:
    value = str(value or "")
    return "등록 전" if value.startswith("__pending__:") else value or "-"


def _bootstrap() -> None:
    ensure_os_schema()
    # One-time transitional bridge per browser session.  It changes only local DB
    # rows and does not call marketplace/supplier mutation APIs.
    if not st.session_state.get("os_bridge_done"):
        try:
            st.session_state["os_bridge_result"] = migrate_legacy_to_os()
        except Exception as exc:
            st.session_state["os_bridge_error"] = str(exc)
        st.session_state["os_bridge_done"] = True


def _hero() -> None:
    st.markdown(
        """
        <style>
          .block-container{max-width:1320px;padding-top:1.2rem;padding-bottom:5rem}
          .os-hero{padding:24px 28px;border-radius:18px;background:linear-gradient(135deg,#0f172a,#1e293b 58%,#312e81);color:white;margin-bottom:14px}
          .os-hero h1{font-size:28px;margin:0;font-weight:850}.os-hero p{margin:7px 0 0;color:#cbd5e1}
          [data-testid="stMetric"]{background:#fff;border:1px solid #e2e8f0;padding:12px;border-radius:12px}
        </style>
        <div class="os-hero">
          <h1>⚡ Seller OS</h1>
          <p>자동화가 반복 작업을 처리하고, 사람은 승인 · 예외처리 · 전략결정만 합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _approve_work(row: dict) -> None:
    approval_id = int(row["id"])
    decided = decide_approval(approval_id, approve=True, actor="seller")
    if not decided.get("ok"):
        st.error(decided.get("error", "승인 실패"))
        return

    action_type = row.get("action_type")
    if action_type == "marketplace.publish":
        queued = enqueue_task(
            "listing_publish",
            {"approval_id": approval_id},
            queue_name="dangerous",
            dedupe_key=f"listing_publish:{approval_id}",
        )
        if queued.get("ok"):
            st.success(f"승인 완료 · 위험 작업 #{queued['task_id']}을 전용 큐에 접수했습니다.")
        else:
            st.error(queued.get("error", "위험 작업 큐 접수 실패"))
        return

    if action_type == "supplier.order":
        # Approval changes only local fulfillment state.  No supplier API is called
        # until a verified v3 SupplierOrderPort driver is installed for that supplier.
        moved = approve_fulfillment_state(approval_id)
        if moved.get("ok"):
            st.success("발주 승인 완료 · 검증된 공급처 주문 드라이버가 있을 때만 실제 실행됩니다.")
        else:
            st.error(moved.get("error", "발주 승인 처리 실패"))
        return

    st.success("승인했습니다.")


def _work_queue() -> None:
    data = get_dashboard()
    m = data["metrics"]
    health = data["health"]
    work = data["work_queue"]

    a, b, c, d, e = st.columns(5)
    a.metric("상품", m["products"])
    b.metric("판매중", m["active_listings"])
    c.metric("처리중 주문", m["open_orders"])
    d.metric("실제 순이익", _krw(m["profit_krw"]))
    e.metric("내가 처리할 일", len(work))

    st.markdown("### 오늘 할 일")
    st.caption("자동화가 처리하지 못했거나 실제 비용·외부 변경 때문에 사람 판단이 필요한 항목만 표시합니다.")
    if not work:
        st.success("현재 직접 처리해야 할 업무가 없습니다.")
    for row in work:
        with st.container(border=True):
            left, body, right = st.columns([1.1, 5, 2], vertical_alignment="center")
            left.markdown("**" + {
                "approval": "승인", "order_exception": "주문 예외",
                "fulfillment_failed": "발주 실패", "task_failed": "자동화 실패",
            }.get(row["kind"], row["kind"]) + "**")
            body.markdown(f"**{row['title']}**")
            body.caption(f"{row['detail']} · {_dt(row.get('created_at'))}")
            right.write(row["action"])
            if row["kind"] == "approval":
                c1, c2, _ = st.columns([1, 1, 4])
                if c1.button("승인", key=f"approve_{row['id']}", type="primary", use_container_width=True):
                    _approve_work(row)
                    st.rerun()
                if c2.button("거절", key=f"reject_{row['id']}", use_container_width=True):
                    result = decide_approval(int(row["id"]), approve=False, actor="seller")
                    if result.get("ok"):
                        st.success("거절했습니다.")
                        st.rerun()
                    else:
                        st.error(result.get("error", "거절 실패"))

    if health["unlinked_order_items"]:
        st.warning(f"내부 Product/Variant에 연결되지 않은 주문 품목 {health['unlinked_order_items']}건이 있습니다.")


def _products() -> None:
    st.markdown("### 상품")
    st.caption("SupplierOffer → Product/Variant → Listing을 하나의 상품 상세에서 관리합니다.")
    f1, f2 = st.columns([2, 1])
    keyword = f1.text_input("상품 검색", placeholder="상품명 · SKU · 브랜드", key="os_product_keyword")
    status = f2.selectbox(
        "상태", ["", "draft", "review", "ready", "active", "paused", "archived"],
        format_func=lambda x: "전체" if not x else _status(x), key="os_product_status",
    )
    rows = list_products(status=status, keyword=keyword, limit=300)
    if not rows:
        st.info("조건에 맞는 상품이 없습니다. 새 상품은 통합 상품 소싱에서 확보하세요.")
        return
    st.dataframe([
        {"ID": x["id"], "SKU": x["sku"], "상품": x["name"], "브랜드": x["brand"],
         "상태": _status(x["status"]), "판매채널": x["channels"] or "-", "수정": _dt(x["updated_at"])}
        for x in rows
    ], use_container_width=True, hide_index=True)

    choices = {f"#{x['id']} · {x['name'][:70]}": x["id"] for x in rows}
    detail = get_product_detail(choices[st.selectbox("상품 상세", list(choices), key="os_product_select")])
    if not detail:
        return
    with st.container(border=True):
        st.markdown(f"#### {detail['name']}")
        st.caption(f"{detail['sku']} · {_status(detail['status'])} · {detail['brand'] or '브랜드 없음'} · {detail['category'] or '카테고리 없음'}")
        a, b, c, d = st.columns(4)
        a.metric("Variant", len(detail["variants"]))
        b.metric("공급 Offer", len(detail["offers"]))
        c.metric("Listing", len(detail["listings"]))
        d.metric("판매중 채널", sum(1 for x in detail["listings"] if x["status"] == "active"))

        t1, t2, t3 = st.tabs(["공급처 · 옵션", "판매채널", "콘텐츠"])
        with t1:
            if detail["variants"]:
                st.dataframe(detail["variants"], use_container_width=True, hide_index=True)
            if detail["offers"]:
                st.dataframe([
                    {"공급처": x["supplier"], "상품ID": x["supplier_product_id"], "공급가": x["supply_price_krw"],
                     "배송비": x["shipping_fee_krw"], "재고": x["stock_qty"], "MOQ": x["moq"],
                     "리드타임": x["lead_time_days"], "상태": x["status"], "동기화": _dt(x["last_synced_at"])}
                    for x in detail["offers"]
                ], use_container_width=True, hide_index=True)
            else:
                st.warning("연결된 공급처 Offer가 없습니다.")
        with t2:
            if detail["listings"]:
                st.dataframe([
                    {"채널": x["platform"], "상태": _status(x["status"]), "판매가": x["sale_price_krw"],
                     "외부상품ID": _external_id(x["external_product_id"]), "오류": x["error"]}
                    for x in detail["listings"]
                ], use_container_width=True, hide_index=True)
            else:
                st.info("아직 판매채널에 등록되지 않았습니다.")
            if detail["status"] in {"ready", "active"}:
                c1, c2 = st.columns(2)
                if c1.button("쿠팡 등록 승인 요청", key=f"cp_{detail['id']}", use_container_width=True):
                    r = request_listing_publish(detail["id"], "coupang", actor="seller")
                    st.success("오늘 할 일에 승인 요청을 만들었습니다.") if r.get("ok") else st.error(r.get("error", "요청 실패"))
                if c2.button("스마트스토어 등록 승인 요청", key=f"ss_{detail['id']}", use_container_width=True):
                    r = request_listing_publish(detail["id"], "smartstore", actor="seller")
                    st.success("오늘 할 일에 승인 요청을 만들었습니다.") if r.get("ok") else st.error(r.get("error", "요청 실패"))
        with t3:
            content = detail["content"]
            a, b, c = st.columns(3)
            a.metric("대표 이미지", len(content.get("images") or []))
            b.metric("상세 이미지", len(content.get("detail_images") or []))
            c.metric("상세 HTML", "있음" if content.get("detail_html") else "없음")
            st.caption("이미지 · SEO · 상세페이지는 별도 상품을 만들지 않고 이 Product의 콘텐츠를 갱신합니다.")


def _orders() -> None:
    st.markdown("### 주문 · 배송")
    st.caption("SalesOrderItem → SupplierOffer → Fulfillment → Tracking을 한 흐름으로 추적합니다.")
    a, b = st.columns([2, 1])
    status = a.selectbox(
        "주문 상태", ["", "new", "exception", "ready_to_fulfill", "fulfilling", "shipped", "completed", "cancelled"],
        format_func=lambda x: "전체" if not x else _status(x), key="os_order_status",
    )
    if b.button("신규 주문 동기화", type="primary", use_container_width=True):
        r = enqueue_task("order_sync", {"hours": 24}, queue_name="sync", dedupe_key="order_sync")
        st.success(f"작업 #{r['task_id']} 접수") if r.get("ok") else st.error(r.get("error", "접수 실패"))

    rows = list_orders(status=status, limit=300)
    if not rows:
        st.info("수집된 주문이 없습니다.")
        return
    st.dataframe([
        {"ID": x["id"], "채널": x["platform"], "주문번호": x["order_no"], "상태": _status(x["status"]),
         "수취인": x["receiver"], "품목": x["items"], "예외": x["exceptions"], "주문금액": x["amount_krw"], "주문시각": _dt(x["ordered_at"])}
        for x in rows
    ], use_container_width=True, hide_index=True)

    choices = {f"#{x['id']} · {x['platform']} · {x['order_no']}": x["id"] for x in rows}
    detail = get_order_detail(choices[st.selectbox("주문 상세", list(choices), key="os_order_select")])
    if not detail:
        return
    with st.container(border=True):
        st.markdown(f"#### {detail['platform'].upper()} · {detail['order_no']}")
        st.caption(f"{_status(detail['status'])} · {detail['receiver_name']} · {_dt(detail['ordered_at'])}")
        st.write(f"배송지: {detail['shipping_address'] or '-'}")
        if detail["shipping_message"]:
            st.write(f"배송메모: {detail['shipping_message']}")
        for item in detail["items"]:
            with st.container(border=True):
                left, right = st.columns([5, 1.5])
                left.markdown(f"**{item['product_name'] or '상품 미확인'}**")
                left.caption(f"수량 {item['quantity']} · {_krw(item['unit_sale_price_krw'])} · Product #{item['product_id'] or '-'} · Variant #{item['variant_id'] or '-'}")
                right.error(item["exception_code"]) if item["exception_code"] else right.success(_status(item["status"]))
                f = item["fulfillment"]
                if f:
                    st.write(f"공급처 {f['supplier_code'] or '-'} · 발주번호 {f['supplier_order_id'] or '-'} · {_status(f['status'])}")
                    if f["tracking_number"]:
                        st.write(f"송장 {f['delivery_company'] or '-'} {f['tracking_number']}")
                    if f["failure_message"]:
                        st.error(f["failure_message"])
                elif item["product_id"] and item["status"] in {"ready", "new"}:
                    if st.button("공급처 실제 발주 승인 요청", key=f"fulfill_{item['id']}", use_container_width=True):
                        r = request_order_fulfillment(item["id"], actor="seller")
                        st.success("오늘 할 일에 발주 승인 요청을 만들었습니다.") if r.get("ok") else st.error(r.get("error", "발주 요청 실패"))
                s = item["settlement"]
                if s:
                    st.caption(f"실제 손익 · 매출 {_krw(s['gross_revenue_krw'])} / 공급가 {_krw(s['supply_cost_krw'])} / 순이익 {_krw(s['net_profit_krw'])}")


def _profit() -> None:
    st.markdown("### 수익")
    st.caption("예상마진과 실제 정산을 구분하며, 실제 수익은 주문품목 단위 원장을 기준으로 합니다.")
    data = get_profit_summary(); s = data["summary"]
    a, b, c, d, e = st.columns(5)
    a.metric("매출", _krw(s["gross_revenue_krw"]))
    b.metric("공급가", _krw(s["supply_cost_krw"]))
    c.metric("플랫폼 수수료", _krw(s["platform_fee_krw"]))
    d.metric("순이익", _krw(s["net_profit_krw"]))
    e.metric("순이익률", f"{s['margin_pct']:.2f}%")
    st.markdown("#### 채널별")
    st.dataframe([{"채널": x["platform"], "정산품목": x["orders"], "매출": x["revenue_krw"], "순이익": x["profit_krw"]} for x in data["by_platform"]], use_container_width=True, hide_index=True)
    st.markdown("#### 최근 손익 원장")
    st.dataframe(data["recent"], use_container_width=True, hide_index=True) if data["recent"] else st.info("아직 정산 원장이 없습니다.")


def _settings() -> None:
    st.markdown("### 설정 · 자동화")
    st.caption("연결 · 작업큐 · 데이터 건강도 · 감사이력을 한 곳에서 봅니다.")
    conn = get_connection_summary()
    st.markdown("#### 연결")
    st.dataframe([
        {"구분": x["kind"], "서비스": x["name"], "상태": "설정됨" if x["configured"] else "확인 필요", "기능": ", ".join(x["capabilities"])}
        for x in conn["rows"]
    ], use_container_width=True, hide_index=True)

    st.markdown("#### 안전 자동화")
    cols = st.columns(4)
    actions = [
        (cols[0], "카탈로그 동기화", "catalog_sync", {}, "catalog_sync"),
        (cols[1], "주문 동기화", "order_sync", {"hours": 24}, "order_sync"),
        (cols[2], "데이터 관계 복구", "data_reconcile", {"remote": True}, "data_reconcile"),
        (cols[3], "전체 이미지 복구", "image_repair", {"include_marketplaces": True}, "image_repair"),
    ]
    for col, label, task_type, payload, dedupe in actions:
        if col.button(label, use_container_width=True, key=f"task_{task_type}"):
            r = enqueue_task(task_type, payload, queue_name="sync", dedupe_key=dedupe)
            st.success(f"작업 #{r['task_id']} 접수") if r.get("ok") else st.error(r.get("error", "작업 큐 실패"))

    st.markdown("#### 데이터 건강도")
    h = get_os_health(); a, b, c, d = st.columns(4)
    a.metric("미연결 주문품목", h["unlinked_order_items"])
    b.metric("미처리 Fulfillment", h["unfulfilled_order_items"])
    c.metric("승인 대기", h["pending_approvals"])
    d.metric("실패 작업", h["failed_tasks"] + h["failed_operations"])

    ops = get_operations_summary(limit=40)
    t1, t2, t3 = st.tabs(["백그라운드 작업", "위험 작업 실행이력", "감사 로그"])
    with t1:
        st.dataframe(ops["tasks"], use_container_width=True, hide_index=True) if ops["tasks"] else st.info("작업 이력이 없습니다.")
    with t2:
        st.dataframe(ops["operations"], use_container_width=True, hide_index=True) if ops["operations"] else st.info("외부 변경 작업 이력이 없습니다.")
    with t3:
        st.dataframe(ops["audit"], use_container_width=True, hide_index=True) if ops["audit"] else st.info("감사 이력이 없습니다.")
    st.info("재고 사입 PurchaseOrder/MOQ는 위탁판매 기본 업무에서 제외합니다. 외부 변경은 Approval + Idempotency Gate를 통과합니다.")


def render_seller_os_v3() -> None:
    _bootstrap(); _hero()
    work, products, orders, profit, settings = st.tabs(["🎯 오늘 할 일", "📦 상품", "🚚 주문 · 배송", "💰 수익", "⚙️ 설정 · 자동화"])
    with work: _work_queue()
    with products: _products()
    with orders: _orders()
    with profit: _profit()
    with settings: _settings()
