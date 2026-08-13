"""도매꾹/온채널 공급처 연동 화면 공통 UI."""
from __future__ import annotations

from typing import Any

import streamlit as st

from app.config import get_settings
from app.media.image_display import fetch_display_image
from app.pipeline import import_product
from app.suppliers.registry import get_adapter


_META = {
    "domeggook": {
        "name": "도매꾹",
        "icon": "🏷️",
        "subtitle": "공식 Open API 상품 검색 · 상세조회 · AutoSellerAI 상품 등록",
        "env": ["DOMEGGOOK_API_KEY"],
        "optional_env": ["DOMEGGOOK_USER_ID", "DOMEGGOOK_PASSWORD"],
        "note": "상품조회는 Open API KEY만으로 동작합니다. 구매주문/발주 등 Private API는 별도 권한 승인이 필요합니다.",
    },
    "onchannel": {
        "name": "온채널",
        "icon": "🛍️",
        "subtitle": "판매사 로그인 세션 · 상품 검색 · 상세조회 · AutoSellerAI 상품 등록",
        "env": ["ONCHANNEL_LOGIN_ID", "ONCHANNEL_LOGIN_PW"],
        "optional_env": [],
        "note": "현재 상품 수집은 온채널 판매사 계정 로그인 세션 방식으로 동작합니다. 온채널의 쇼핑몰 API 연동 기능과는 별개입니다.",
    },
}


def _configured(supplier_id: str) -> bool:
    s = get_settings()
    if supplier_id == "domeggook":
        return bool((s.domeggook_api_key or "").strip())
    if supplier_id == "onchannel":
        return bool((s.onchannel_login_id or "").strip() and (s.onchannel_login_pw or "").strip())
    return False


def _connection_test(supplier_id: str) -> dict[str, Any]:
    if supplier_id == "domeggook":
        from app.suppliers.domeggook_openapi import test_connection
        return test_connection()
    if supplier_id == "onchannel":
        from app.suppliers.onchannel import reset_client, _get_client, is_logged_in
        try:
            reset_client()
            _get_client()
            if is_logged_in():
                return {"ok": True, "mode": "판매사 로그인 세션"}
            return {"ok": False, "error": "온채널 로그인이 확인되지 않았습니다. ID/PW 또는 로그인 정책을 확인하세요."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "지원하지 않는 공급처"}


def _rows(items) -> list[dict[str, Any]]:
    return [
        {
            "상품코드": p.raw_id,
            "상품명": p.name,
            "공급가": int(p.supply_price or 0),
            "MOQ": int(p.moq or 1),
            "재고": int(p.stock or 0),
            "배송비": int(p.shipping_fee or 0),
            "카테고리": p.category,
            "대표이미지": (p.images or [""])[0],
        }
        for p in items
    ]


def _render_preview(url: str, source_url: str) -> None:
    data = fetch_display_image(str(url or ""), str(source_url or ""))
    if data:
        st.image(data, width=260)
    else:
        st.warning("이미지 URL은 발견했지만 미리보기를 불러오지 못했습니다. 원본 페이지 또는 전체 이미지 복구에서 다시 확인하세요.")


def render_supplier_workspace(supplier_id: str) -> None:
    meta = _META[supplier_id]
    key = f"supplier_{supplier_id}"
    configured = _configured(supplier_id)
    adapter = get_adapter(supplier_id)

    st.markdown(f"# {meta['icon']} {meta['name']} 연동")
    st.caption(meta["subtitle"])

    c1, c2, c3 = st.columns(3)
    c1.metric("공급처", meta["name"])
    c2.metric("인증정보", "설정됨" if configured else "미설정")
    c3.metric("어댑터", "활성" if adapter and adapter.is_available() else "비활성")

    with st.expander("🔐 최초 설정", expanded=not configured):
        st.write(meta["note"])
        lines = [f"{name}=값" for name in meta["env"] + meta["optional_env"]]
        st.code("\n".join(lines), language="bash")
        st.caption("프로젝트 루트 .env에 입력한 뒤 Streamlit을 다시 시작하세요. 비밀번호/API KEY는 화면이나 로그에 출력하지 않습니다.")

    st.divider()
    st.markdown("## 1. 연결 상태")
    if st.button(f"🔌 {meta['name']} 연결 테스트", type="primary", key=f"{key}_test"):
        with st.spinner(f"{meta['name']} 연결 확인 중..."):
            result = _connection_test(supplier_id)
        st.session_state[f"{key}_connection"] = result
    result = st.session_state.get(f"{key}_connection")
    if result:
        if result.get("ok"):
            extra = f" · 검색 가능 상품 {result.get('total'):,}건" if result.get("total") is not None else ""
            st.success(f"연결 성공{extra}")
        else:
            st.error(result.get("error", "연결 실패"))

    st.markdown("## 2. 상품 검색")
    a, b, c, d = st.columns([2.2, 1, 1, 1])
    keyword = a.text_input("검색어", placeholder="예: 차량용 청소기", key=f"{key}_keyword")
    limit = int(b.number_input("검색 개수", min_value=1, max_value=100, value=20, step=5, key=f"{key}_limit"))
    min_price = int(c.number_input("최소 공급가", min_value=0, value=1000, step=1000, key=f"{key}_min_price"))
    max_moq = int(d.number_input("최대 MOQ", min_value=1, value=1, step=1, key=f"{key}_moq"))

    if st.button("🔎 상품 검색", type="primary", use_container_width=True, key=f"{key}_search"):
        if not keyword.strip():
            st.warning("검색어를 입력하세요.")
        elif not adapter or not adapter.is_available():
            st.error("공급처 인증정보가 설정되지 않았습니다.")
        else:
            with st.spinner(f"{meta['name']} 상품 검색 중..."):
                items = adapter.search(keyword.strip(), limit=limit, min_price=min_price, moq=max_moq)
            st.session_state[f"{key}_items"] = items
            if not items:
                st.warning("검색 결과가 없습니다. 인증 상태, 검색어, MOQ/가격 조건을 확인하세요.")

    items = st.session_state.get(f"{key}_items", [])
    if items:
        st.dataframe(_rows(items), use_container_width=True, hide_index=True)
        choices = {f"{p.raw_id} · {p.name[:60]}": p for p in items}
        selected_label = st.selectbox("상세 확인/등록할 상품", list(choices), key=f"{key}_selected")
        selected = choices[selected_label]

        st.markdown("## 3. 상품 상세 · AutoSellerAI 등록")
        if st.button("📄 최신 상세정보 조회", key=f"{key}_detail"):
            with st.spinner("공급처에서 최신 상세정보와 대표/상세 이미지를 조회 중..."):
                detail = adapter.get_product(selected.raw_id)
            if detail:
                st.session_state[f"{key}_detail_product"] = detail
            else:
                st.error("상품 상세정보를 가져오지 못했습니다.")

        detail = st.session_state.get(f"{key}_detail_product")
        if not detail or detail.raw_id != selected.raw_id:
            detail = selected

        with st.container(border=True):
            st.markdown(f"### {detail.name}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("공급가", f"{detail.supply_price:,.0f}원")
            m2.metric("MOQ", detail.moq)
            m3.metric("재고", detail.stock)
            m4.metric("배송비", f"{detail.shipping_fee:,.0f}원")
            if detail.images:
                _render_preview(detail.images[0], detail.raw_url)
                st.caption(f"대표 {len(detail.images)}장 · 상세 {len(detail.detail_images)}장 수집")
            else:
                st.warning("대표 이미지를 아직 찾지 못했습니다. ‘최신 상세정보 조회’를 실행한 뒤에도 없으면 원본 페이지 구조를 점검해야 합니다.")
            st.caption(f"상품코드: {detail.raw_id} · 원본: {detail.raw_url}")

            markup = st.number_input("판매가 배수", min_value=1.0, max_value=10.0, value=2.0, step=0.1, key=f"{key}_markup")
            default_sell = max(100, int(float(detail.supply_price or 0) * float(markup) / 100) * 100)
            sell_price = st.number_input("AutoSellerAI 판매가", min_value=0, value=default_sell, step=100, key=f"{key}_sell")
            use_ai = st.checkbox("AI 상품명·상세설명 최적화", value=True, key=f"{key}_ai")
            if st.button("📥 AutoSellerAI 상품으로 등록", type="primary", use_container_width=True, key=f"{key}_import"):
                if detail.supply_price <= 0:
                    st.error("공급가가 0원입니다. 로그인/권한 또는 상세정보를 먼저 확인하세요.")
                else:
                    with st.spinner("상품 등록 중..."):
                        imported = import_product(supplier_id, detail.raw_id, float(sell_price), use_ai)
                    if imported.get("status") in {"imported", "updated"}:
                        st.success(f"등록 완료 · 상품 #{imported.get('id')} · {imported.get('name')}")
                    else:
                        st.error(imported.get("error", "등록 실패"))
    else:
        st.info("연결 테스트 후 상품을 검색하면 공급가·MOQ·재고·배송비를 확인하고 AutoSellerAI로 등록할 수 있습니다.")

    st.divider()
    st.markdown("## 4. 전체 판매 흐름")
    st.write(f"**{meta['name']} 상품 → AutoSellerAI 상품 DB → AI 선별/SEO/가격검증 → 쿠팡·스마트스토어 등록 → 주문 → 공급처 발주 → 송장 → 정산**")
    if supplier_id == "domeggook":
        st.warning("도매꾹 실제 구매주문/자동발주는 Private API 권한 승인이 필요한 쓰기 작업이므로 원큐 운영의 승인 단계에서 별도로 처리해야 합니다.")
    else:
        st.info("온채널은 상품별 판매승인이 필요한 경우가 있으므로 승인 상태를 확인한 뒤 판매채널 등록 단계로 넘기는 구조를 유지합니다.")
