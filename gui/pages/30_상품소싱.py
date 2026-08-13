"""공급처 통합 상품소싱 화면.

도매꾹/도매매/온채널/오너클랜을 메뉴별로 돌아다니지 않고
검색 → 비교 → 선택 → 내부 상품등록까지 한 화면에서 처리한다.
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from app.pipeline import import_product
from app.suppliers.registry import list_registered, search_all
from gui.korean_runtime import apply_korean_patch

apply_korean_patch()
st.set_page_config(page_title="상품 소싱 | 오토셀러 AI", page_icon="🔎", layout="wide")

LABELS = {
    "domeggook": "도매꾹",
    "domemai": "도매매",
    "onchannel": "온채널",
    "ownerclan": "오너클랜",
}

st.markdown("# 🔎 상품 소싱")
st.caption("여러 공급처를 따로 탐색하지 않고 한 번 검색해서 공급가·배송비·재고·MOQ를 비교합니다.")

registered = list_registered()
available_ids = [x["supplier_id"] for x in registered if x.get("available")]

with st.container(border=True):
    cols = st.columns(max(1, len(registered)))
    for col, item in zip(cols, registered):
        col.metric(
            LABELS.get(item["supplier_id"], item.get("display_name", item["supplier_id"])),
            "연결됨" if item.get("available") else "설정 필요",
        )

if not available_ids:
    st.warning("연결된 공급처가 없습니다. 왼쪽의 ‘연동 설정’에서 공급처 인증정보를 먼저 확인하세요.")

s1, s2, s3, s4 = st.columns([2.8, 2.0, 1.2, 1.2])
keyword = s1.text_input("검색어", placeholder="예: 무선 청소기, 캠핑 랜턴")
selected_suppliers = s2.multiselect(
    "공급처",
    options=[x["supplier_id"] for x in registered],
    default=available_ids,
    format_func=lambda x: LABELS.get(x, x),
)
min_price = s3.number_input("최소 공급가", min_value=0, value=3000, step=1000)
limit = s4.selectbox("공급처별", [10, 20, 30, 50], index=1, format_func=lambda x: f"{x}개")

if st.button("🔍 통합 검색", type="primary", use_container_width=True):
    if not keyword.strip():
        st.warning("검색어를 입력하세요.")
    else:
        with st.spinner("연결된 공급처를 순서대로 검색하고 있습니다..."):
            items = search_all(
                keyword.strip(),
                limit_per_supplier=int(limit),
                min_price=int(min_price),
                suppliers=selected_suppliers,
            )
        # 비교하기 쉽게 공급가 → 배송비 순 정렬
        items.sort(key=lambda x: (float(x.supply_price or 0) <= 0, float(x.supply_price or 0), float(x.shipping_fee or 0)))
        st.session_state["sourcing_results"] = items
        st.session_state["sourcing_keyword"] = keyword.strip()

items = st.session_state.get("sourcing_results", [])
if items:
    st.markdown(f"### 검색 결과 · {len(items)}개")
    st.caption("공급가가 확인된 상품을 우선 표시합니다. 판매가는 플랫폼 수수료·배송비·광고비까지 검증한 뒤 확정하세요.")

    rows = []
    for item in items:
        rows.append({
            "공급처": LABELS.get(item.supplier_id, item.supplier_id),
            "상품코드": item.raw_id,
            "상품명": item.name,
            "공급가": float(item.supply_price or 0),
            "배송비": float(item.shipping_fee or 0),
            "재고": int(item.stock or 0),
            "MOQ": int(item.moq or 1),
            "원산지": item.origin or "",
            "이미지": len(item.images or []),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    options = list(range(len(items)))
    selected_index = st.selectbox(
        "가져올 상품 선택",
        options,
        format_func=lambda i: f"[{LABELS.get(items[i].supplier_id, items[i].supplier_id)}] {items[i].name} · {items[i].supply_price:,.0f}원",
    )
    product = items[selected_index]

    with st.container(border=True):
        image_col, info_col = st.columns([1.4, 3.6])
        with image_col:
            if product.images:
                st.image(product.images[0], use_container_width=True)
            else:
                st.info("대표 이미지 없음")
        with info_col:
            st.markdown(f"#### {product.name}")
            a, b, c, d = st.columns(4)
            a.metric("공급가", f"{product.supply_price:,.0f}원")
            b.metric("배송비", f"{product.shipping_fee:,.0f}원")
            c.metric("재고", f"{product.stock:,}")
            d.metric("MOQ", product.moq)
            st.caption(f"{LABELS.get(product.supplier_id, product.supplier_id)} · {product.raw_id} · {product.origin or '원산지 미확인'}")

            base = max(float(product.supply_price or 0) + float(product.shipping_fee or 0), 1000)
            suggested = int((base / max(1 - 0.25 - 0.11, 0.3)) / 100) * 100
            sell_price = st.number_input("초기 판매가", min_value=100, value=max(100, suggested), step=100)
            use_ai = st.checkbox("AI 상품명·상세설명 초안 생성", value=True)
            if st.button("📥 AutoSellerAI 상품으로 가져오기", type="primary", use_container_width=True):
                with st.spinner("상품 상세·이미지를 다시 확인하고 내부 상품으로 등록 중..."):
                    result = import_product(product.supplier_id, product.raw_id, float(sell_price), use_ai)
                if result.get("status") in {"imported", "updated"}:
                    st.success(f"등록 완료 · #{result.get('id')} · {result.get('name')}")
                    st.page_link("pages/00_AutoSeller_Main.py", label="📦 상품관리로 이동", use_container_width=True)
                else:
                    st.error(result.get("error", "상품 등록 실패"))
else:
    st.info("검색하면 도매꾹·도매매·온채널·오너클랜 결과를 한 화면에서 비교할 수 있습니다.")
