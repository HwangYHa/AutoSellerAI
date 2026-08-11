"""AutoSellerAI 전체 프로세스 사용자 매뉴얼."""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="사용자 매뉴얼 | AutoSeller AI", page_icon="📘", layout="wide")

st.markdown("# 📘 AutoSeller AI 사용자 매뉴얼")
st.caption("상품 수집부터 주문·배송·소셜커머스·순이익 학습까지 전체 운영 흐름을 단계별로 안내합니다.")

with st.expander("🚀 처음 시작하는 사용자를 위한 10분 설정", expanded=True):
    st.markdown(
        """
1. 프로젝트 루트의 `.env.example`을 복사해 `.env`를 만듭니다.
2. 네이버 스마트스토어, 쿠팡, Claude AI, Threads 등 사용할 서비스의 인증정보를 입력합니다.
3. `pip install -r requirements.txt`로 Python 패키지를 설치합니다.
4. 로컬 실행은 `streamlit run gui/app.py`, 전체 서비스 실행은 `docker compose up --build`를 사용합니다.
5. 브라우저에서 `http://localhost:8501`에 접속합니다.
6. 먼저 **통합 운영 화면**에서 상품을 수집·등록하고, 이후 **소셜커머스** 기능을 사용합니다.
        """
    )

st.markdown("## 🧭 전체 업무 흐름")
steps = [
    ("1", "공급처 상품 수집", "도매꾹·도매매·온채널 등 공급처에서 원본 상품을 수집합니다."),
    ("2", "AI 상품 선별", "가격·마진·경쟁도·SEO 가능성 등을 기준으로 판매 후보를 선별합니다."),
    ("3", "상품 콘텐츠 생성", "상품명, 키워드, 상세설명, FAQ 등 판매용 콘텐츠를 생성합니다."),
    ("4", "판매채널 등록", "네이버 스마트스토어와 쿠팡에 상품을 등록하고 가격·재고를 동기화합니다."),
    ("5", "주문 수집", "판매채널 주문을 자동 수집해 내부 주문과 연결합니다."),
    ("6", "공급처 발주·배송", "공급처 발주, 송장 수집, 판매채널 발송처리를 진행합니다."),
    ("7", "정산·순이익 계산", "매출, 공급가, 수수료, 배송비, 광고비, 반품비, 부가세를 반영해 순이익을 계산합니다."),
    ("8", "스레드 콘텐츠 생성", "상품 DB를 기반으로 AI가 스레드용 콘텐츠를 생성합니다."),
    ("9", "게시·클릭·구매 귀속", "추적 링크를 통해 클릭을 기록하고 스마트스토어·쿠팡 주문과 연결합니다."),
    ("10", "순이익 기반 AI 학습", "게시물·캠페인별 실제 순이익과 콘텐츠 점수를 계산해 다음 콘텐츠 전략에 반영합니다."),
]
for no, title, desc in steps:
    with st.container(border=True):
        st.markdown(f"### {no}. {title}")
        st.write(desc)

st.markdown("## ⚡ 1. 통합 운영 화면")
st.info("왼쪽 메뉴의 **운영 → 통합 운영 화면**에서 기존 AutoSellerAI 핵심 기능을 사용합니다.")
with st.expander("상품 수집·선별·등록", expanded=False):
    st.markdown(
        """
- 공급처 계정/API가 정상 연결되어 있는지 먼저 확인합니다.
- 공급처에서 수집한 원본 데이터는 별도로 보존되며, 판매 후보만 상품 마스터로 이동합니다.
- 최소 마진, 가격 범위, 재고 여부 등을 확인합니다.
- AI 점수는 참고 지표이며 최종 등록 전 상품명·가격·옵션·배송조건을 확인하는 것이 좋습니다.
- 온채널처럼 승인 절차가 필요한 공급처는 승인 완료 후 등록 단계를 진행합니다.
        """
    )
with st.expander("SEO·상품 콘텐츠", expanded=False):
    st.markdown(
        """
- 상품명 후보와 검색 키워드를 생성합니다.
- 네이버 쇼핑 검색·데이터랩 연동 시 실제 검색 데이터를 참고할 수 있습니다.
- 상품 DB에 없는 인증·성능·배송기간·최저가를 AI가 임의 생성하지 않도록 검수합니다.
- SEO 반영은 사람 승인 후 적용하는 운영을 권장합니다.
        """
    )
with st.expander("주문·발주·송장·배송", expanded=False):
    st.markdown(
        """
- 네이버/쿠팡 주문을 먼저 수집합니다.
- 내부 상품과 주문 상품이 정상 매칭되었는지 확인합니다.
- 공급처 발주 후 공급처 주문번호와 송장번호를 기록합니다.
- 판매채널 송장 등록까지 완료되어야 배송 자동화가 정상 종료됩니다.
- 취소·반품 주문은 일반 완료 주문과 분리해 정산합니다.
        """
    )
with st.expander("정산·수익", expanded=False):
    st.markdown(
        """
순이익 계산에는 다음 항목을 사용합니다.

- 총 매출
- 공급 원가
- 플랫폼 수수료
- 고객에게 받은 배송비와 실제 배송비 차액
- 광고비
- 반품·교환 비용
- 부가세 예상액

소셜커머스 수익 학습은 가능하면 **실제 정산 Order 데이터**를 최우선으로 사용합니다. 정산 전 주문은 보수적으로 추정되며 이후 다시 계산됩니다.
        """
    )

st.markdown("## 🧵 2. 스레드 소셜커머스")
st.info("왼쪽 메뉴의 **소셜커머스 → 스레드 운영센터**에서 댓글 영업과 즉시 게시를 관리합니다.")
with st.expander("대시보드", expanded=False):
    st.write("게시물, 댓글, 구매 가능성이 높은 고객, 발송 답글, 콘텐츠 초안, 예약 게시, 추적 클릭, 귀속 주문을 한 번에 확인합니다.")
with st.expander("AI 콘텐츠", expanded=False):
    st.markdown(
        """
1. 판매할 상품을 선택합니다.
2. 콘텐츠 유형을 선택합니다: 문제 해결형 / 경험·공감형 / 질문형 / 비교형 / 목록형.
3. 댓글 유도 키워드를 입력합니다.
4. AI 콘텐츠 후보를 생성합니다.
5. 생성 결과를 읽고 과장·허위 표현이 없는지 검수합니다.
        """
    )
with st.expander("즉시 게시·예약 게시", expanded=False):
    st.markdown(
        """
- 텍스트, 이미지, 영상, 슬라이드형 게시물을 지원합니다.
- 이미지/영상은 Meta가 접근 가능한 공개 URL이어야 합니다.
- 예약 게시 시간은 화면에서 한국시간으로 입력하며 DB에는 UTC로 저장됩니다.
- `threads-scheduler` 서비스가 예약 시각을 확인해 자동 게시합니다.
        """
    )
with st.expander("댓글 영업·구매 가능 고객", expanded=False):
    st.markdown(
        """
- 댓글을 구매 의도, 배송, 재고, 가격, 상품정보, 불만, 반품 등으로 분류합니다.
- 구매의도 점수가 높은 댓글은 **구매 가능 고객**에서 우선 확인합니다.
- 불만·반품·민감 문의는 자동 답변보다 사람 검토를 우선합니다.
- AI 답글함에서 초안을 수정한 뒤 승인·발행할 수 있습니다.
        """
    )
with st.expander("자동 답글 규칙", expanded=False):
    st.write("특정 키워드에 대한 고정 답변 규칙을 만들 수 있습니다. 우선순위가 낮은 숫자일수록 먼저 평가하도록 운영하는 방식을 권장합니다.")

st.markdown("## 📈 3. 성장 자동화")
st.info("**소셜커머스 → 성장 자동화**에서는 콘텐츠 생성부터 구매 귀속까지 판매 퍼널을 관리합니다.")
with st.expander("추적 링크 생성", expanded=False):
    st.markdown(
        """
1. 상품과 최종 판매처를 선택합니다.
2. 스마트스토어/쿠팡 실제 상품 URL을 입력합니다.
3. 캠페인 식별값을 입력합니다.
4. 추적 링크를 생성해 스레드 콘텐츠에 사용합니다.
5. 고객이 링크를 클릭하면 클릭 시각과 익명화된 식별정보가 기록됩니다.
        """
    )
with st.expander("구매 귀속", expanded=False):
    st.markdown(
        """
외부 마켓 주문 API는 AutoSellerAI의 클릭 식별자를 그대로 돌려주지 않으므로 자동 구매 귀속은 **확률 방식**입니다.

- 같은 상품
- 같은 판매처
- 클릭 이후 발생한 주문
- 설정된 귀속 시간 범위

를 기준으로 연결합니다. 운영자가 확인한 주문은 **확정 귀속**으로 승격할 수 있습니다.
        """
    )

st.markdown("## 💹 4. 수익 인텔리전스")
st.info("**소셜커머스 → 수익 인텔리전스**에서 조회수가 아닌 실제 순이익을 기준으로 콘텐츠를 평가합니다.")
with st.expander("콘텐츠 점수", expanded=False):
    st.markdown(
        """
콘텐츠 점수는 다음 지표를 종합합니다.

- 순이익률
- 총 순이익
- 클릭당 순이익
- 구매 전환율
- 구매 귀속 신뢰도
- 반품·취소 품질

클릭이 많아도 손실이 나는 게시물은 높은 점수를 받지 못합니다. 표본이 적을 때는 과적합을 막기 위해 점수를 중립값 쪽으로 보정합니다.
        """
    )
with st.expander("AI 전략 학습", expanded=False):
    st.markdown(
        """
- 상품별로 수익성이 좋은 콘텐츠 유형과 피해야 할 유형을 저장합니다.
- 최소 주문 표본이 확보된 유형만 우선 유형 후보가 됩니다.
- 충분한 주문 데이터가 쌓이면 다음 AI 콘텐츠 생성 시 우선 유형을 자동 적용합니다.
- 실제 정산 데이터가 추정 데이터보다 우선합니다.
        """
    )

st.markdown("## 🔐 5. API·인증 설정")
api_rows = [
    ("Claude AI", "CLAUDE_API_KEY", "AI 콘텐츠·분석"),
    ("네이버 스마트스토어", "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET", "상품·주문·배송 연동"),
    ("쿠팡", "COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY / COUPANG_VENDOR_ID", "상품·주문·배송 연동"),
    ("네이버 검색", "NAVER_SEARCH_CLIENT_ID / NAVER_SEARCH_CLIENT_SECRET", "검색·SEO 분석"),
    ("Meta Threads", "THREADS_APP_ID / THREADS_APP_SECRET 등", "스레드 게시·OAuth"),
    ("도매꾹·도매매", "DOMEGGOOK_API_KEY / DOMEMAI_API_KEY", "공급처 상품 수집"),
    ("온채널", "ONCHANNEL_LOGIN_ID / ONCHANNEL_LOGIN_PW", "공급처 연동"),
    ("텔레그램", "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID", "운영 알림"),
]
st.dataframe([{"서비스": a, "필요 설정": b, "용도": c} for a, b, c in api_rows], use_container_width=True, hide_index=True)
st.warning("실제 API 키·비밀번호는 GitHub에 커밋하지 말고 로컬 `.env` 또는 안전한 Secret 저장소에서 관리하세요.")

st.markdown("## 🐳 6. 실행·점검 명령어")
st.code("""# 가상환경 활성화 후
pip install -r requirements.txt
pytest -q

# Docker 전체 실행
docker compose down
docker compose up --build

# 백그라운드 실행
docker compose up -d --build

# 상태 확인
docker compose ps

# 로그 확인
docker compose logs --tail=200
""", language="bash")

st.markdown("## 🧯 7. 자주 발생하는 문제")
troubleshooting = [
    ("스레드 연결 버튼이 안 보임", "Social API가 실행 중인지 확인하고 Meta 앱 ID/시크릿/리다이렉트 URI를 확인합니다."),
    ("이미지·영상 게시 실패", "미디어 URL이 외부에서 인증 없이 접근 가능한 공개 HTTPS URL인지 확인합니다."),
    ("예약 게시가 실행되지 않음", "threads-scheduler와 Redis가 실행 중인지 `docker compose ps`로 확인합니다."),
    ("구매 귀속이 0건", "추적 클릭이 주문보다 먼저 발생했는지, 상품/플랫폼 매칭과 귀속 시간 범위를 확인합니다."),
    ("순이익이 추정으로 표시됨", "해당 PlatformOrder와 같은 주문번호의 실제 정산 Order가 생성되었는지 확인합니다."),
    ("AI 전략이 바로 안 바뀜", "1건의 주문으로 전략이 흔들리지 않도록 최소 표본 조건이 있습니다. 충분한 귀속 주문이 쌓여야 자동 적용됩니다."),
    ("pytest에서 app 모듈 오류", "저장소 루트에서 실행하고 `pytest.ini`가 존재하는지 확인합니다."),
]
for title, answer in troubleshooting:
    with st.expander(title):
        st.write(answer)

st.markdown("## ✅ 운영 권장 순서")
st.success("**상품 데이터 정확성 → 주문/정산 정확성 → 소셜 추적 정확성 → AI 자동화 확대** 순서로 운영하세요. AI가 아무리 좋아도 원가·수수료·주문 연결이 틀리면 수익 학습 결과도 틀어집니다.")
