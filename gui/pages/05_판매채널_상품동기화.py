"""쿠팡·스마트스토어 외부 판매상품을 AutoSellerAI로 역동기화하는 운영 화면."""
from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
from sqlalchemy import desc, func, select

from app.db import Listing, Product, get_db, init_db
from app.pipeline import sync_platform_catalog
from app.platforms.coupang import reset_coupang_uploader
from app.platforms.smartstore import reset_smartstore_uploader
from gui.korean_runtime import apply_korean_patch

apply_korean_patch()
st.set_page_config(page_title="판매채널 상품 동기화 | 오토셀러 AI", page_icon="🔄", layout="wide")
init_db()

st.markdown("## 🔄 판매채널 상품 동기화")
st.caption(
    "쿠팡 Wing 또는 스마트스토어 판매자센터에서 직접 등록·수정한 상품을 "
    "AutoSellerAI 내부 상품관리로 가져옵니다. 이 기능은 판매채널의 상품을 읽기만 하며, 동기화 버튼만으로 외부 상품을 수정하지 않습니다."
)

with st.container(border=True):
    st.markdown("### 동기화 실행")
    st.info(
        "기존 통합 운영 화면의 ‘새로고침’은 로컬 DB만 다시 표시합니다. "
        "판매자센터에서 직접 등록/수정한 상품은 이 화면에서 판매채널 동기화를 실행해야 반영됩니다."
    )

    c1, c2, c3 = st.columns(3)
    run_ss = c1.button("🟢 스마트스토어 동기화", type="primary", use_container_width=True)
    run_cp = c2.button("🟠 쿠팡 동기화", type="primary", use_container_width=True)
    run_all = c3.button("🔄 두 채널 모두 동기화", use_container_width=True)


def _run(platform: str) -> dict:
    # .env/설정 변경 직후에도 최신 키를 사용하도록 싱글턴 초기화
    if platform == "smartstore":
        reset_smartstore_uploader()
    else:
        reset_coupang_uploader()
    return sync_platform_catalog(platform)


def _show_result(platform_name: str, result: dict) -> None:
    if not result.get("ok"):
        st.error(f"{platform_name} 동기화 실패: {result.get('error', '알 수 없는 오류')}")
        st.caption("401/403이면 API 인증·권한을, 400이면 요청값/판매자 ID를 확인하세요. 오류 문구를 그대로 복사해 전달하면 원인을 추적할 수 있습니다.")
        return

    cols = st.columns(5)
    values = [
        ("발견", result.get("total_found", 0)),
        ("신규", result.get("created", 0)),
        ("기존 연결", result.get("linked", 0)),
        ("변경 반영", result.get("updated", 0)),
        ("변경 없음", result.get("skipped", 0)),
    ]
    for col, (label, value) in zip(cols, values):
        col.metric(label, value)
    st.success(f"{platform_name} 동기화 완료")


if run_ss or run_all:
    with st.spinner("스마트스토어 판매자센터 상품 전체 목록을 가져오는 중..."):
        res = _run("smartstore")
    _show_result("스마트스토어", res)
    st.session_state["last_market_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if run_cp or run_all:
    with st.spinner("쿠팡 Wing 판매상품 전체 목록을 가져오는 중... 상품 상세 조회 때문에 시간이 걸릴 수 있습니다."):
        res = _run("coupang")
    _show_result("쿠팡", res)
    st.session_state["last_market_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if st.session_state.get("last_market_sync"):
    st.caption(f"마지막 수동 동기화: {st.session_state['last_market_sync']}")

st.divider()
st.markdown("### 현재 내부에 연결된 판매채널 상품")
with get_db() as db:
    ss_count = int(db.scalar(select(func.count()).select_from(Listing).where(Listing.platform == "smartstore", Listing.status == "success")) or 0)
    cp_count = int(db.scalar(select(func.count()).select_from(Listing).where(Listing.platform == "coupang", Listing.status == "success")) or 0)
    imported_count = int(db.scalar(select(func.count()).select_from(Product).where(Product.source.in_(["smartstore_import", "coupang_import"]))) or 0)
    recent = list(db.scalars(
        select(Product)
        .where(Product.source.in_(["smartstore_import", "coupang_import"]))
        .order_by(desc(Product.updated_at))
        .limit(100)
    ).all())

m1, m2, m3 = st.columns(3)
m1.metric("스마트스토어 연결", ss_count)
m2.metric("쿠팡 연결", cp_count)
m3.metric("외부 직접등록 상품", imported_count)

if recent:
    st.dataframe([
        {
            "상품 ID": p.id,
            "유입 경로": "스마트스토어 직접등록" if p.source == "smartstore_import" else "쿠팡 직접등록",
            "판매채널 상품번호": p.source_id,
            "상품명": p.name,
            "판매가": float(p.sell_price or 0),
            "카테고리": p.category,
            "브랜드": p.brand,
            "상태": p.status,
            "갱신일": p.updated_at.strftime("%Y-%m-%d %H:%M:%S") if p.updated_at else "",
        }
        for p in recent
    ], use_container_width=True, hide_index=True)
else:
    st.warning("아직 판매자센터에서 직접 가져온 상품이 없습니다. 위 동기화를 실행하고 결과 또는 오류 메시지를 확인하세요.")

st.divider()
st.markdown("### 정상 동작 기준")
st.write(
    "판매자센터에 AutoSellerAI 밖에서 등록한 상품이 있다면 동기화 결과의 ‘발견’이 1 이상이어야 합니다. "
    "처음 가져오는 상품은 ‘신규’, 기존 상품명·가격 등이 판매자센터에서 바뀌었다면 ‘변경 반영’이 증가합니다."
)
st.page_link("pages/00_AutoSeller_Main.py", label="📦 통합 운영의 상품관리로 이동", use_container_width=True)
