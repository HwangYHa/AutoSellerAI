"""오토셀러AI 공통 사용자 도움말 UI — 원큐 운영 순서와 동일한 프로세스 정의."""
from __future__ import annotations

import streamlit as st

PROCESS_STEPS = [
    ("01", "초기 설정 · API 연동", "판매채널·공급처·AI 연결 상태를 먼저 확인합니다.", "🚀 원큐 운영 / 오너클랜 연동"),
    ("02", "기존 판매상품 동기화", "쿠팡·스마트스토어 판매자센터의 기존 상품을 내부 DB와 맞춥니다.", "🔄 판매채널 상품 동기화"),
    ("03", "공급처 상품 수집", "오너클랜·도매꾹·도매매·온채널에서 판매 후보를 가져옵니다.", "⚡ 통합 운영 → 상품수집"),
    ("04", "AI 상품 선별", "마진·수요·경쟁·재고·공급 안정성을 기준으로 판매 후보를 선별합니다.", "⚡ 통합 운영 → 시장분석/상품관리"),
    ("05", "상품 이미지 수집", "공급처 API와 상품 페이지 태그에서 대표/상세 이미지를 복원합니다.", "🖼️ 상품 이미지 · AI 상세페이지"),
    ("06", "AI 상세페이지 보강", "원본 상세자료가 부족한 경우에만 reference 기반 AI 이미지를 선택 제작합니다.", "🖼️ 상품 이미지 · AI 상세페이지"),
    ("07", "SEO · GEO · AEO", "상품명·키워드·FAQ·상세정보를 검색과 AI 답변 노출에 맞게 최적화합니다.", "⚡ 통합 운영 → 검색 최적화"),
    ("08", "판매가 · 순이익 검증", "공급가·배송비·수수료·광고비까지 반영해 손실 판매를 차단합니다.", "⚡ 통합 운영 → 가격 자동화"),
    ("09", "판매채널 등록", "검수 완료 상품을 스마트스토어·쿠팡에 실제 등록합니다.", "⚡ 통합 운영 → 업로드"),
    ("10", "주문 수집", "스마트스토어·쿠팡 신규 주문을 통합 수집합니다.", "⚡ 통합 운영 → 주문"),
    ("11", "공급처 발주", "상품·옵션·수취정보를 검증하고 공급처에 발주합니다.", "⚡ 통합 운영 → 발주"),
    ("12", "송장 · 배송", "공급처의 실제 택배사와 송장을 회수해 판매채널에 발송 처리합니다.", "⚡ 통합 운영 → 주문/배송"),
    ("13", "정산 · 실제 순이익", "매출·원가·수수료·배송·광고·반품·세금을 반영합니다.", "⚡ 통합 운영 → 정산·세금"),
    ("14", "스레드 판매", "SEO·GEO·AEO 기반 콘텐츠 → 게시 → 댓글 영업 → 추적 링크를 운영합니다.", "🧵 스레드 운영센터 / 성장 자동화"),
    ("15", "구매 귀속 · 수익 학습", "실제 마켓 주문과 순이익을 콘텐츠 점수와 다음 판매전략에 반영합니다.", "💹 수익 인텔리전스"),
]


def render_sidebar_help() -> None:
    st.sidebar.markdown("### 📘 사용 도움말")
    st.sidebar.page_link("pages/90_사용자_매뉴얼.py", label="전체 사용자 매뉴얼", icon="📘")
    st.sidebar.caption("처음이라면 ‘원큐 운영’에서 현재 단계부터 확인하세요.")


def render_process_overview(*, expanded: bool = True) -> None:
    with st.expander("🧭 전체 판매 흐름 01 → 15", expanded=expanded):
        st.caption("초기 연동부터 상품·주문·정산·광고·수익 학습까지 아래 번호 순서가 AutoSellerAI의 표준 운영 순서입니다.")
        cols = st.columns(5)
        for idx, (no, title, desc, location) in enumerate(PROCESS_STEPS):
            with cols[idx % 5]:
                with st.container(border=True):
                    st.markdown(f"#### {no}. {title}")
                    st.write(desc)
                    st.caption(f"📍 {location}")
        st.page_link("pages/01_원큐_운영.py", label="🚀 현재 상태부터 원큐로 진행", icon="🚀", use_container_width=True)
        st.page_link("pages/90_사용자_매뉴얼.py", label="📘 단계별 전체 사용자 매뉴얼 열기", use_container_width=True)


def render_context_help(title: str, steps: list[str], *, next_action: str | None = None) -> None:
    with st.expander(f"❓ {title} 사용 방법", expanded=False):
        for i, step in enumerate(steps, 1):
            st.markdown(f"**{i}.** {step}")
        if next_action:
            st.info(f"다음 단계: {next_action}")
        st.page_link("pages/01_원큐_운영.py", label="원큐 운영에서 전체 순서 확인", icon="🚀")
        st.page_link("pages/90_사용자_매뉴얼.py", label="전체 매뉴얼에서 자세히 보기", icon="📘")
