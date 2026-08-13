"""오토셀러AI Seller OS v2 사용자 매뉴얼."""
from __future__ import annotations

import streamlit as st

from gui.help_center import PROCESS_STEPS


def render_manual() -> None:
    st.markdown("# 📘 오토셀러 AI 사용자 매뉴얼")
    st.caption("평소에는 Seller OS만 사용하고, 새 상품이 필요할 때 통합 상품 소싱, 연결 문제가 있을 때만 연동 설정을 사용합니다.")

    st.info(
        "**핵심 규칙:** 연결 → 상품 확보 → 판매 준비 → 채널 등록 → 주문 → 발주/배송 → 정산 → 성장. "
        "세부 기능을 따로 외우지 말고 이 8단계만 기억하세요."
    )

    st.markdown("## 가장 많이 쓰는 화면")
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.markdown("### 📦 Seller OS")
            st.write("상품·주문·배송·수익을 일상적으로 관리하는 기본 화면입니다.")
            st.page_link("pages/00_AutoSeller_Main.py", label="Seller OS", use_container_width=True)
    with c2:
        with st.container(border=True):
            st.markdown("### 🔎 통합 상품 소싱")
            st.write("도매꾹·도매매·온채널·오너클랜을 한 번에 검색하고 비교합니다.")
            st.page_link("pages/30_상품소싱.py", label="상품 소싱", use_container_width=True)
    with c3:
        with st.container(border=True):
            st.markdown("### 🚀 원큐 자동화")
            st.write("현재 상태를 진단하고 안전한 동기화를 실행한 뒤 다음 한 가지 작업을 안내합니다.")
            st.page_link("pages/01_원큐_운영.py", label="원큐 자동화", use_container_width=True)

    st.markdown("## 8단계 표준 운영")
    for no, title, desc, location in PROCESS_STEPS:
        with st.container(border=True):
            left, right = st.columns([0.7, 5.3])
            left.markdown(f"### {no}")
            with right:
                st.markdown(f"### {title}")
                st.write(desc)
                st.caption(f"📍 {location}")

    st.markdown("## 1. 처음 실행")
    with st.expander("프로그램 시작", expanded=True):
        st.code(
            "git switch main\n"
            "git pull origin main\n"
            "pip install -r requirements.txt\n"
            "streamlit run gui/app.py",
            language="bash",
        )
        st.write("브라우저에서 `http://localhost:8501`에 접속합니다.")
        st.warning("`.env`를 수정했다면 Streamlit을 Ctrl+C로 완전히 종료한 뒤 다시 실행하세요.")

    st.markdown("## 2. Seller OS 사용법")
    with st.expander("📦 상품", expanded=True):
        st.markdown(
            """
- 검색창 하나로 상품명·SKU·상품번호를 찾습니다.
- 상태, 공급처, 판매채널, `조치 필요만` 필터로 목록을 줄입니다.
- 카드에는 판매가·공급가·단순마진·이미지 수·채널 상태만 표시합니다.
- 여러 상품을 선택하면 한 번에 쿠팡/스마트스토어 등록 또는 상태 변경이 가능합니다.
- 이미지가 깨지거나 없으면 상단 **이미지 복구**를 사용합니다.
- 상품 하나의 옵션·상세이미지·판매채널 번호가 필요할 때만 **상세**를 엽니다.
            """
        )
        st.success("목표: 목록을 훑었을 때 ‘무슨 상품이고, 얼마에 팔며, 어디에 등록됐고, 문제가 있는지’를 바로 알 수 있어야 합니다.")

    with st.expander("🚚 주문 · 배송"):
        st.markdown(
            """
1. **신규 주문 수집**을 실행합니다.
2. 신규 주문의 상품·수량·수취인·주소를 확인합니다.
3. 실제 공급처 발주는 금액이 발생하므로 확인 후 실행합니다.
4. 공급처에서 실제 택배사와 송장이 나온 뒤 Seller OS에 입력합니다.
5. **송장 등록**으로 쿠팡/스마트스토어 발송처리까지 연결합니다.
            """
        )

    with st.expander("💰 수익"):
        st.markdown(
            """
Seller OS의 수익 탭은 예상 매출이 아니라 실제 운영 결과를 봅니다.

- 매출
- 공급 원가
- 플랫폼 수수료
- 실제 배송비
- 광고비
- 반품·교환 비용
- 세금 추정치
- 최종 순이익
            """
        )

    with st.expander("🔌 연동 · 시스템"):
        st.write("평소에는 들어갈 필요가 없습니다. API 키 변경, 인증 오류, 판매채널 동기화 오류가 있을 때만 사용합니다.")
        st.markdown(
            """
- **쿠팡·스마트스토어 연동:** 기존 판매상품 역동기화와 인증 진단
- **오너클랜 연동:** JWT/GraphQL 판매사 API 진단
- **도매꾹 연동:** Open API 연결 진단
- **온채널 연동:** 로그인 세션 연결 진단
            """
        )

    st.markdown("## 3. 새 상품을 판매하기")
    st.markdown(
        """
1. **통합 상품 소싱**에서 검색합니다.
2. 공급처별 공급가·배송비·재고·MOQ를 비교합니다.
3. 상품 하나를 AutoSellerAI로 가져옵니다.
4. Seller OS 상품 탭에서 이미지, 상품명, 판매가, 마진을 확인합니다.
5. 원본 상세자료가 부족할 때만 **이미지 · AI 상세페이지**를 사용합니다.
6. 상품을 선택하고 판매채널을 지정해 등록합니다.
7. 이후 주문은 Seller OS 주문·배송에서 처리합니다.
        """
    )

    st.markdown("## 4. 이미지가 깨질 때")
    st.markdown(
        """
쿠팡 API는 이미지 값을 완전한 웹 URL이 아니라 CDN 상대경로로 돌려주는 경우가 있습니다. Seller OS v2는 이를 저장 전에 절대 URL로 정규화하고, 기존 DB의 잘못된 이미지 문자열도 표시하지 않습니다.

**복구 순서**
1. Seller OS → 상품
2. **이미지 복구** 클릭
3. 기존 DB 이미지 경로 정리
4. 쿠팡 상품 상세를 다시 동기화
5. 복구할 수 없는 이미지는 깨진 아이콘 대신 `이미지 없음`으로 표시
        """
    )

    st.markdown("## 5. 스마트스토어 `Invalid salt`가 뜰 때")
    st.markdown(
        """
`NAVER_CLIENT_ID / NAVER_CLIENT_SECRET`은 **네이버 Commerce API 센터에서 발급된 한 쌍**이어야 합니다.
검색 API의 `NAVER_SEARCH_CLIENT_ID / NAVER_SEARCH_CLIENT_SECRET`과 섞으면 안 됩니다.

Commerce API Client Secret은 `$2a$...` 형태의 bcrypt salt입니다. 연동 화면에서 형식 검사를 통과한 뒤 동기화를 실행하세요.
        """
    )

    st.markdown("## 6. 기능을 어디서 찾아야 하나")
    rows = [
        ["상품을 찾는다", "통합 상품 소싱"],
        ["상품을 수정·선택·등록한다", "Seller OS → 상품"],
        ["이미지를 보완한다", "Seller OS → 상품 → 이미지 복구 / 이미지·AI 상세페이지"],
        ["주문을 받는다", "Seller OS → 주문·배송"],
        ["송장을 넣는다", "Seller OS → 주문·배송"],
        ["실제 수익을 본다", "Seller OS → 수익"],
        ["API 연결 문제를 고친다", "연동 설정"],
        ["다음에 뭘 해야 할지 모르겠다", "원큐 자동화"],
    ]
    st.dataframe(rows, column_config={0: "하려는 일", 1: "사용할 화면"}, hide_index=True, use_container_width=True)

    st.markdown("## 7. 하루 운영 순서")
    st.markdown(
        """
**1) Seller OS → 주문·배송:** 신규 주문과 송장 대기 확인  
**2) Seller OS → 상품:** 조치 필요 상품만 확인  
**3) 필요할 때만 통합 상품 소싱:** 새 판매 후보 확보  
**4) Seller OS → 수익:** 실제 순이익 확인  
**5) 선택적으로 스레드 판매/수익 학습:** 수익성이 확인된 상품 중심으로 마케팅
        """
    )

    st.success("운영 기준: 평소에는 Seller OS 하나로 끝내고, 필요한 경우에만 소싱·연동·AI 화면으로 빠져나갑니다.")
