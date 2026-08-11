"""오토셀러AI 공통 사용자 도움말 UI."""
from __future__ import annotations

import streamlit as st

PROCESS_STEPS = [
    ("1", "상품 수집", "공급처에서 판매 후보 상품을 가져옵니다.", "⚡ 통합 운영 → 상품수집"),
    ("2", "상품 선별", "마진·경쟁도·재고·판매 가능성을 확인합니다.", "⚡ 통합 운영 → 시장분석/상품관리"),
    ("3", "검색 최적화", "상품명·키워드·상세정보를 판매채널에 맞게 정리합니다.", "⚡ 통합 운영 → 검색 최적화"),
    ("4", "상품 등록", "스마트스토어·쿠팡에 상품을 등록합니다.", "⚡ 통합 운영 → 업로드"),
    ("5", "주문·배송", "주문 수집 → 공급처 발주 → 송장 → 발송까지 처리합니다.", "⚡ 통합 운영 → 주문/재고/발주"),
    ("6", "정산·순이익", "매출·원가·수수료·배송비·반품비를 반영합니다.", "⚡ 통합 운영 → 정산·세금"),
    ("7", "스레드 판매", "AI 콘텐츠 생성 → 게시 → 댓글 영업 → 추적 링크를 운영합니다.", "🧵 스레드 운영센터 / 성장 자동화"),
    ("8", "수익 학습", "실제 주문과 순이익을 콘텐츠 전략에 다시 반영합니다.", "💹 수익 인텔리전스"),
]


def render_sidebar_help() -> None:
    """모든 주요 화면에서 접근할 수 있는 도움말 진입점."""
    st.sidebar.markdown("### 📘 사용 도움말")
    st.sidebar.page_link("pages/90_사용자_매뉴얼.py", label="전체 사용자 매뉴얼", icon="📘")
    st.sidebar.caption("처음이라면 매뉴얼의 ‘전체 업무 흐름’부터 확인하세요.")


def render_process_overview(*, expanded: bool = True) -> None:
    """전체 프로세스를 한눈에 보여주는 시작 안내."""
    with st.expander("🧭 처음 사용하시나요? 전체 판매 흐름 보기", expanded=expanded):
        st.caption("아래 순서대로 진행하면 상품 발굴부터 판매·정산·AI 학습까지 연결됩니다.")
        cols = st.columns(4)
        for idx, (no, title, desc, location) in enumerate(PROCESS_STEPS):
            with cols[idx % 4]:
                with st.container(border=True):
                    st.markdown(f"#### {no}. {title}")
                    st.write(desc)
                    st.caption(f"📍 {location}")
        st.page_link(
            "pages/90_사용자_매뉴얼.py",
            label="📘 단계별 전체 사용자 매뉴얼 열기",
            use_container_width=True,
        )


def render_context_help(title: str, steps: list[str], *, next_action: str | None = None) -> None:
    """각 기능 화면에서 현재 해야 할 일을 짧게 안내한다."""
    with st.expander(f"❓ {title} 사용 방법", expanded=False):
        for i, step in enumerate(steps, 1):
            st.markdown(f"**{i}.** {step}")
        if next_action:
            st.info(f"다음 단계: {next_action}")
        st.page_link("pages/90_사용자_매뉴얼.py", label="전체 매뉴얼에서 자세히 보기", icon="📘")
