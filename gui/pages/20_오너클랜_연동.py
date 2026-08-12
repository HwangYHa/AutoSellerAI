"""오너클랜 판매사 API 연동센터."""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from app.config import get_settings
from app.pipeline import import_product
from app.suppliers.adapter_ownerclan import OwnerClanAdapter
from app.suppliers.ownerclan import get_ownerclan_client, reset_ownerclan_client
from gui.korean_runtime import apply_korean_patch

apply_korean_patch()
st.set_page_config(page_title="오너클랜 연동 | 오토셀러 AI", page_icon="🏬", layout="wide")

st.markdown("# 🏬 오너클랜 판매사 API 연동")
st.caption("JWT 인증 · GraphQL 상품 조회 · 내부 상품 등록 · 주문/송장 조회")

s = get_settings()
env_label = "운영(Production)" if (s.ownerclan_environment or "production").lower() == "production" else "테스트(Sandbox)"
configured = bool((s.ownerclan_username or "").strip() and (s.ownerclan_password or "").strip())

c1, c2, c3 = st.columns(3)
c1.metric("API 유형", "판매사 API")
c2.metric("환경", env_label)
c3.metric("인증정보", "설정됨" if configured else "미설정")

with st.expander("🔐 최초 설정 방법", expanded=not configured):
    st.markdown(
        """
1. 오너클랜 API 센터에서 **판매사 API**를 신청합니다.
2. 가능하면 Sandbox로 먼저 연결을 확인한 뒤 운영 환경으로 전환합니다.
3. 프로젝트 루트 `.env`에 아래 값을 입력합니다.
        """
    )
    st.code(
        "OWNERCLAN_USERNAME=판매사ID\n"
        "OWNERCLAN_PASSWORD=판매사PW\n"
        "OWNERCLAN_ENVIRONMENT=production",
        language="bash",
    )
    st.warning("판매사 비밀번호와 JWT 토큰은 화면/로그에 출력하지 마세요.")

st.divider()

st.markdown("## 1. 연결 상태")
if st.button("🔌 JWT + GraphQL 연결 테스트", type="primary", use_container_width=False):
    reset_ownerclan_client()
    with st.spinner("오너클랜 인증 및 GraphQL 연결 확인 중..."):
        result = get_ownerclan_client().test_connection()
    if result.get("ok"):
        st.success(f"연결 성공 · {result.get('environment')} · GraphQL 사용 가능")
    else:
        st.error(result.get("error", "연결 실패"))

st.markdown("## 2. 오너클랜 상품 가져오기")
st.caption("현재는 공식 문서로 확인된 `item(key:)` 단건 조회를 우선 사용합니다. 오너클랜 상품코드를 입력하세요.")

left, right = st.columns([0.9, 1.3], gap="large")
with left:
    item_key = st.text_input("오너클랜 상품코드", placeholder="예: W000000")
    markup = st.number_input("판매가 배수", min_value=1.0, max_value=10.0, value=2.0, step=0.1)
    use_ai = st.checkbox("AI 상품명·상세설명 최적화", value=True)
    lookup = st.button("🔎 상품 조회", type="primary", use_container_width=True)

if lookup and item_key.strip():
    adapter = OwnerClanAdapter()
    with st.spinner("오너클랜 상품 조회 중..."):
        product = adapter.get_product(item_key.strip())
    if not product:
        st.error("상품을 가져오지 못했습니다. API 권한, 상품코드, 운영/테스트 환경을 확인하세요.")
    else:
        st.session_state["ownerclan_product"] = product

product = st.session_state.get("ownerclan_product")
with right:
    if product:
        with st.container(border=True):
            st.markdown(f"### {product.name}")
            a, b, c = st.columns(3)
            a.metric("오너클랜 공급가", f"{product.supply_price:,.0f}원")
            b.metric("재고", f"{product.stock:,}")
            b.caption("옵션 재고 합계 기준")
            c.metric("옵션 그룹", len(product.options))
            st.caption(f"상품코드: {product.raw_id}")
            if product.options:
                st.json(product.options, expanded=False)

            suggested = max(10, int(product.supply_price * float(markup) / 10) * 10)
            sell_price = st.number_input(
                "AutoSellerAI 판매가",
                min_value=10,
                value=suggested,
                step=100,
                key="ownerclan_sell_price",
            )
            if st.button("📥 AutoSellerAI 상품으로 등록", type="primary", use_container_width=True):
                with st.spinner("상품 등록 중..."):
                    result = import_product("ownerclan", product.raw_id, float(sell_price), use_ai)
                if result.get("status") in {"imported", "updated"}:
                    st.success(f"등록 완료 · #{result.get('id')} · {result.get('name')}")
                else:
                    st.error(result.get("error", "등록 실패"))
    else:
        st.info("왼쪽에서 오너클랜 상품코드를 조회하면 상품 정보가 표시됩니다.")

st.divider()
st.markdown("## 3. 오너클랜 주문·송장 조회")
st.caption("쿠팡/스마트스토어 주문을 오너클랜에 자동 발주하기 전에, 판매사 주문 API가 정상 조회되는지 확인합니다.")

period = st.selectbox("조회 기간", [1, 7, 30, 90], index=1, format_func=lambda x: f"최근 {x}일")
if st.button("📦 최근 오너클랜 주문 조회", use_container_width=False):
    now = datetime.now(timezone.utc)
    date_from = int((now - timedelta(days=int(period))).timestamp())
    date_to = int(now.timestamp())
    try:
        with st.spinner("주문 조회 중..."):
            result = get_ownerclan_client().list_orders(first=100, date_from=date_from, date_to=date_to)
        edges = result.get("edges") or []
        rows = []
        for edge in edges:
            node = edge.get("node") or {}
            products = node.get("products") or []
            rows.append({
                "주문코드": node.get("key", ""),
                "상태": node.get("status", ""),
                "상품수": len(products),
                "송장번호": ", ".join(str(p.get("trackingNumber") or "") for p in products if p.get("trackingNumber")),
                "택배사": ", ".join(str(p.get("shippingCompanyName") or "") for p in products if p.get("shippingCompanyName")),
                "생성시각": node.get("createdAt", ""),
            })
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("해당 기간에 조회된 오너클랜 주문이 없습니다.")
        if (result.get("pageInfo") or {}).get("hasNextPage"):
            st.caption("100건을 초과한 주문이 있습니다. 자동화 작업에서는 cursor로 다음 페이지까지 계속 수집합니다.")
    except Exception as exc:
        st.error(str(exc))

st.divider()
st.markdown("## 4. 최종 자동화 흐름")
st.markdown(
    "**오너클랜 상품 → AutoSellerAI → 스마트스토어/쿠팡 등록 → 마켓 주문 수집 → "
    "오너클랜 주문 시뮬레이션 → 자동 발주 → 송장 조회 → 마켓 송장 등록 → 정산·순이익 계산**"
)
st.info("자동 발주는 실제 비용이 발생하는 쓰기 작업이므로, API 연결과 주문 시뮬레이션 검증 후 별도 안전장치를 켜는 방식으로 연결합니다.")
