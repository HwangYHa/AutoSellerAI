"""오토셀러AI 공통 사용자 도움말 UI — Seller OS v2의 8단계 프로세스."""
from __future__ import annotations

import streamlit as st

PROCESS_STEPS = [
    ("01", "연결 점검", "판매채널·공급처·AI 인증 상태를 확인합니다.", "Seller OS → 연동·시스템"),
    ("02", "상품 확보 · 동기화", "공급처를 한 번에 검색하고 기존 쿠팡·스마트스토어 상품도 내부 DB와 맞춥니다.", "통합 상품 소싱 / 판매채널 동기화"),
    ("03", "판매 준비", "AI 선별·이미지·SEO·판매가·예상수익 검증을 상품관리에서 끝냅니다.", "Seller OS → 상품"),
    ("04", "판매채널 등록", "검수된 상품만 쿠팡·스마트스토어에 실제 등록합니다.", "Seller OS → 상품 → 선택상품 일괄작업"),
    ("05", "주문 수집", "쿠팡·스마트스토어 신규 주문을 한 화면으로 수집합니다.", "Seller OS → 주문·배송"),
    ("06", "발주 · 송장 · 배송", "주문을 확인해 공급처 발주 후 실제 택배사·송장을 판매채널에 반영합니다.", "Seller OS → 주문·배송"),
    ("07", "정산 · 실제 수익", "매출·공급가·수수료·배송·광고·반품·세금을 반영한 실제 수익을 확인합니다.", "Seller OS → 수익"),
    ("08", "마케팅 · 수익 학습", "스레드 콘텐츠와 구매귀속 결과를 실제 순이익에 연결합니다.", "스레드 판매 / 수익 학습"),
]


def render_sidebar_help() -> None:
    st.sidebar.markdown("### 📘 도움말")
    st.sidebar.caption("처음이면 ‘원큐 자동화’에서 다음 할 일만 확인하세요.")


def render_process_overview(*, expanded: bool = True) -> None:
    with st.expander("🧭 전체 운영 흐름 01 → 08", expanded=expanded):
        st.caption("세부 기능을 외울 필요 없이 아래 8개 업무 단위만 순서대로 사용합니다.")
        cols = st.columns(4)
        for idx, (no, title, desc, location) in enumerate(PROCESS_STEPS):
            with cols[idx % 4]:
                with st.container(border=True):
                    st.markdown(f"#### {no}. {title}")
                    st.write(desc)
                    st.caption(f"📍 {location}")
        st.page_link("pages/01_원큐_운영.py", label="🚀 현재 상태와 다음 작업 확인", icon="🚀", use_container_width=True)
        st.page_link("pages/90_사용자_매뉴얼.py", label="📘 사용자 매뉴얼", use_container_width=True)


def render_context_help(title: str, steps: list[str], *, next_action: str | None = None) -> None:
    with st.expander(f"❓ {title} 사용 방법", expanded=False):
        for i, step in enumerate(steps, 1):
            st.markdown(f"**{i}.** {step}")
        if next_action:
            st.info(f"다음 단계: {next_action}")
        st.page_link("pages/01_원큐_운영.py", label="원큐 자동화에서 전체 흐름 확인", icon="🚀")
