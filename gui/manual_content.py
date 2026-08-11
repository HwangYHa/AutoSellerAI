"""오토셀러AI 전체 프로세스 사용자 매뉴얼 본문."""
from __future__ import annotations

import streamlit as st

from gui.help_center import PROCESS_STEPS


def _step_card(no: str, title: str, desc: str, location: str) -> None:
    with st.container(border=True):
        st.markdown(f"### {no}. {title}")
        st.write(desc)
        st.caption(f"📍 메뉴 위치: {location}")


def render_manual() -> None:
    st.markdown("# 📘 오토셀러 AI 사용자 매뉴얼")
    st.caption("처음 설정부터 상품 판매, 주문·배송, 정산, 스레드 판매, 순이익 기반 AI 학습까지 전체 흐름을 단계별로 안내합니다.")

    st.info("처음 사용하는 경우 **① 초기 설정 → ② 상품 판매 운영 → ③ 소셜 판매 자동화** 순서로 진행하세요.")

    top1, top2, top3 = st.columns(3)
    with top1:
        with st.container(border=True):
            st.markdown("#### ① 초기 설정")
            st.write("판매채널·공급처·AI·스레드 인증정보와 실행환경을 준비합니다.")
    with top2:
        with st.container(border=True):
            st.markdown("#### ② 상품 판매 운영")
            st.write("상품 수집 → 선별 → 검색 최적화 → 등록 → 주문·배송 → 정산")
    with top3:
        with st.container(border=True):
            st.markdown("#### ③ 소셜 판매 자동화")
            st.write("콘텐츠 → 게시 → 댓글 영업 → 추적 → 구매 귀속 → 순이익 학습")

    with st.expander("🚀 1. 처음 실행하기", expanded=True):
        st.markdown(
            """
1. 프로젝트 루트에서 `.env.example`을 복사해 `.env`를 만듭니다.
2. 사용할 판매채널·공급처·AI·스레드 인증정보를 입력합니다.
3. 가상환경을 활성화합니다.
4. `pip install -r requirements.txt`를 실행합니다.
5. 화면 실행: `streamlit run gui/app.py`
6. 브라우저에서 `http://localhost:8501`에 접속합니다.
7. Docker 전체 실행이 필요하면 `docker compose up --build`를 사용합니다.
            """
        )
        st.warning("환경변수명, 실제 URL, API 키 값은 번역하거나 임의로 변경하지 마세요.")

    st.markdown("## 🧭 전체 업무 흐름")
    for no, title, desc, location in PROCESS_STEPS:
        _step_card(no, title, desc, location)

    st.markdown("## ⚡ 2. 상품 판매 운영")
    with st.expander("① 상품 수집", expanded=True):
        st.markdown(
            """
- **통합 운영 화면 → 상품수집**으로 이동합니다.
- 공급처 연결 상태를 확인합니다.
- 도매꾹·온채널 등에서 판매 후보를 수집합니다.
- 공급가, 배송비, 재고, 옵션, 반품조건이 없는 상품은 바로 등록하지 않습니다.
- 수집 후 상품관리 화면에서 판매 후보를 다시 검토합니다.
            """
        )
        st.success("완료 기준: 판매 후보 상품이 내부 상품 목록에 생성되어 있어야 합니다.")

    with st.expander("② 상품 선별·시장분석"):
        st.markdown(
            """
- 예상 판매가와 공급가 차이를 확인합니다.
- 플랫폼 수수료와 배송비까지 반영한 실제 마진을 봅니다.
- 경쟁 상품 수, 검색 수요, 리뷰 강도, 재고 안정성을 확인합니다.
- 낮은 마진·높은 반품 위험·불안정한 재고 상품은 제외합니다.
            """
        )
        st.success("완료 기준: 실제로 등록할 상품만 남아 있어야 합니다.")

    with st.expander("③ 검색 최적화·상품 콘텐츠"):
        st.markdown(
            """
- 상품명에 핵심 속성·규격·용도·브랜드를 자연스럽게 반영합니다.
- 검색 키워드와 상품 설명을 생성·검수합니다.
- 상품 데이터에 없는 인증, 성능, 배송기간, 최저가를 AI가 임의 생성하지 않았는지 확인합니다.
- 자동 생성 결과는 승인 후 적용하는 운영을 권장합니다.
            """
        )
        st.success("완료 기준: 등록 가능한 상품명·가격·상세정보가 준비되어 있어야 합니다.")

    with st.expander("④ 스마트스토어·쿠팡 등록"):
        st.markdown(
            """
1. 판매채널 인증정보가 정상인지 확인합니다.
2. 등록할 상품을 선택합니다.
3. 판매가, 재고, 배송비, 옵션을 최종 확인합니다.
4. 스마트스토어·쿠팡에 업로드합니다.
5. 플랫폼 상품번호가 정상 저장됐는지 확인합니다.
            """
        )
        st.success("완료 기준: 상품 상태가 판매 중으로 확인되어야 합니다.")

    with st.expander("⑤ 주문 → 발주 → 송장 → 배송"):
        st.markdown(
            """
1. 판매채널 주문을 수집합니다.
2. 주문 상품과 내부 상품이 정확히 매칭됐는지 확인합니다.
3. 공급처에 발주합니다.
4. 공급처 주문번호를 기록합니다.
5. 송장번호를 수집합니다.
6. 스마트스토어·쿠팡에 송장을 등록하고 발송 처리합니다.
7. 배송 완료 여부를 확인합니다.
8. 취소·반품은 완료 주문과 별도로 관리합니다.
            """
        )
        st.success("완료 기준: 주문이 배송 완료 또는 정상 정산 대기 상태여야 합니다.")

    with st.expander("⑥ 정산·순이익"):
        st.markdown(
            """
순이익에는 다음 항목을 반영합니다.

- 총 매출
- 공급 원가
- 플랫폼 수수료
- 실제 배송비
- 고객에게 받은 배송비
- 광고비
- 반품·교환 비용
- 예상 부가세

실제 정산 Order가 존재하면 실제 데이터를 우선 사용하고, 정산 전에는 보수적인 추정값을 사용합니다.
            """
        )
        st.success("완료 기준: 주문별 순이익과 마진율이 계산되어 있어야 합니다.")

    st.markdown("## 🧵 3. 스레드 소셜 판매")
    with st.expander("① 콘텐츠 생성·게시", expanded=True):
        st.markdown(
            """
1. 스레드 운영센터에서 판매할 상품을 선택합니다.
2. 문제 해결형·경험형·질문형·비교형·목록형 중 콘텐츠 유형을 선택합니다.
3. AI 콘텐츠를 생성합니다.
4. 과장·허위 표현을 검수합니다.
5. 텍스트·이미지·영상·슬라이드형 중 게시 형식을 선택합니다.
6. 즉시 게시하거나 한국시간 기준으로 예약 게시합니다.
            """
        )

    with st.expander("② 댓글 영업·구매 가능 고객"):
        st.markdown(
            """
- 댓글을 구매 의도, 가격, 배송, 재고, 상품정보, 호환성, 불만, 반품 등으로 분류합니다.
- 구매 가능성이 높은 댓글은 **구매 가능 고객**에서 우선 확인합니다.
- AI 답글 초안을 확인한 뒤 발행합니다.
- 불만·반품·민감 문의는 자동 답변보다 사람 검토를 우선합니다.
            """
        )

    with st.expander("③ 추적 링크·구매 귀속"):
        st.markdown(
            """
1. 실제 스마트스토어 또는 쿠팡 상품 링크를 등록합니다.
2. 추적 링크를 생성해 스레드 게시물에 사용합니다.
3. 클릭이 발생하면 클릭 기록이 저장됩니다.
4. 이후 발생한 판매채널 주문과 상품·판매처·시간 범위를 기준으로 연결합니다.
5. 자동 연결은 확률 귀속이며 운영자가 확인한 경우 확정 귀속으로 관리합니다.
            """
        )

    with st.expander("④ 수익 인텔리전스·AI 전략 학습"):
        st.markdown(
            """
- 게시물별 클릭, 주문, 매출, 순이익, 반품, 콘텐츠 점수를 확인합니다.
- 조회수가 높아도 실제 손실이면 좋은 콘텐츠로 평가하지 않습니다.
- 충분한 주문 표본이 쌓이면 수익성이 높은 콘텐츠 유형을 우선 유형으로 학습합니다.
- 다음 AI 콘텐츠 생성 시 수익성이 검증된 유형을 우선 사용합니다.
            """
        )
        st.success("최종 목표: 조회수 최대화가 아니라 실제 순이익이 높은 판매 패턴을 반복하는 것입니다.")

    st.markdown("## 🔐 4. 필요한 외부 연동")
    rows = [
        ["네이버 스마트스토어", "상품·주문·배송", "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET"],
        ["쿠팡", "상품·주문·배송", "COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY / COUPANG_VENDOR_ID"],
        ["Claude AI", "콘텐츠·분석", "CLAUDE_API_KEY"],
        ["메타 스레드", "게시·댓글·계정 인증", "THREADS_APP_ID / THREADS_APP_SECRET 등"],
        ["네이버 검색", "검색·키워드 분석", "NAVER_SEARCH_CLIENT_ID / NAVER_SEARCH_CLIENT_SECRET"],
        ["공급처", "상품 수집", "공급처별 API 키 또는 로그인 정보"],
    ]
    st.dataframe(rows, column_config={0: "서비스", 1: "사용 목적", 2: "설정값"}, hide_index=True, use_container_width=True)

    st.markdown("## 🧯 5. 문제가 생겼을 때 확인 순서")
    with st.expander("화면이 실행되지 않음", expanded=False):
        st.markdown(
            """
1. 프로젝트 루트에서 실행했는지 확인합니다.
2. 가상환경이 활성화되어 있는지 확인합니다.
3. `pip install -r requirements.txt`를 다시 실행합니다.
4. `pytest -q`로 기본 오류를 확인합니다.
5. Docker 사용 시 `docker compose ps`와 로그를 확인합니다.
            """
        )
    with st.expander("판매채널 주문이 안 들어옴"):
        st.markdown("인증정보 → 판매채널 권한 → 주문 조회 기간 → 플랫폼 응답 → 내부 상품 매칭 순서로 확인합니다.")
    with st.expander("스레드 게시가 안 됨"):
        st.markdown("계정 인증 상태 → 토큰 만료 → 공개 미디어 URL → 예약 실행 서비스 → API 응답 순서로 확인합니다.")
    with st.expander("순이익이 이상함"):
        st.markdown("판매가 → 수량 → 공급가 → 플랫폼 수수료 → 배송비 → 광고비 → 반품비 → 부가세 → 실제 정산 Order 존재 여부를 확인합니다.")

    st.markdown("## ✅ 하루 운영 권장 순서")
    st.markdown(
        """
**오전**: 신규 주문 확인 → 발주 → 송장·배송 확인 → 재고 이상 확인  
**오후**: 상품 수집·등록 → 검색 최적화 → 스레드 콘텐츠 생성·예약  
**마감**: 정산·순이익 확인 → 반품/취소 확인 → 수익 인텔리전스 확인 → 다음 콘텐츠 전략 점검
        """
    )
