"""AutoSellerAI Seller OS v3.3 user manual.

This module intentionally keeps the manual inside Streamlit so the operating guide
is available next to the actual controls. Keep menu labels and safety boundaries in
sync with gui/main.py and the Seller OS API.
"""
from __future__ import annotations

import streamlit as st


UPDATED_AT = "2026-09-01"
SELLER_OS_VERSION = "3.3"


def _step(title: str, body: str) -> None:
    with st.container(border=True):
        st.markdown(f"### {title}")
        st.markdown(body)


def _menu_card(title: str, desc: str, path: str) -> None:
    with st.container(border=True):
        st.markdown(f"### {title}")
        st.write(desc)
        st.page_link(path, label="화면 열기", use_container_width=True)


def render_manual() -> None:
    st.markdown("# 📘 AutoSellerAI 사용자 매뉴얼")
    st.caption(f"Seller OS v{SELLER_OS_VERSION} · 최종 업데이트 {UPDATED_AT} · 상품 소싱 → 등록 → 주문/발주 → 콘텐츠/Threads → Tracking → 수익학습까지 한 흐름으로 운영")

    st.info(
        "**운영 원칙:** 반복 작업은 자동화하고, 돈이 나가거나 외부 상태를 바꾸거나 판단이 필요한 작업은 명시적으로 확인합니다. "
        "정상 주문은 자동화가 처리하고 사용자는 카드 승인·가격변동·품절·클레임·매칭 오류·유료 AI 생성·외부 게시 같은 예외와 승인만 관리합니다."
    )

    # ------------------------------------------------------------------
    # 1. 빠른 시작
    # ------------------------------------------------------------------
    st.markdown("## 1. 설치 · 실행 · 업데이트")
    st.write("Windows PowerShell에서 프로젝트 루트로 이동한 뒤 배포 스크립트를 실행합니다.")
    st.code(
        "cd G:\\Dev\\python-workspace\\AutoSellerAI\n"
        "powershell -ExecutionPolicy Bypass -File .\\scripts\\deploy_local.ps1",
        language="powershell",
    )
    st.write("기본 접속 주소는 `http://localhost:8501` 입니다.")

    with st.expander("GitHub 최신 main을 받은 뒤 Docker를 직접 재빌드하는 방법"):
        st.code(
            "git pull origin main\n"
            "docker compose down\n"
            "docker compose up -d --build --force-recreate\n"
            "docker compose ps",
            language="powershell",
        )
        st.caption("Stable Diffusion WebUI를 함께 사용할 때는 Windows WebUI를 먼저 실행한 뒤 AutoSellerAI 컨테이너를 올리는 편이 확인하기 쉽습니다.")

    st.warning("`.env`에는 실제 API 키·토큰·판매자 정보가 있으므로 Git에 커밋하지 않습니다. `.env` 변경 후에는 관련 서비스를 재기동하세요.")

    # ------------------------------------------------------------------
    # 2. Main navigation
    # ------------------------------------------------------------------
    st.markdown("## 2. 메뉴별 역할")
    st.caption("평소에는 Seller OS와 관제 화면을 중심으로 보고, 상품을 성장시키는 작업이 필요할 때 콘텐츠/이미지/Campaign Director 화면을 사용합니다.")

    row1 = st.columns(4)
    menu1 = [
        ("🎯 Seller OS", "오늘 할 일, 상품, 주문·배송, 수익, 시스템 상태를 보는 기본 운영 화면", "main.py"),
        ("🛰️ 주문·발주 관제센터", "주문 → 공급처 → 결제 → 송장 → 판매채널 반영 상태를 추적", "pages/05_Order_Fulfillment_Monitor.py"),
        ("🧭 통합 판매 운영센터", "CS 메모, 태그, 출고보류, 클레임, 재고정책, 정산, 판매 템플릿 관리", "pages/06_통합판매운영센터.py"),
        ("🤖 커머스 자동화 제어센터", "주문·클레임·문의·재고·정산·결제·스케줄러 자동화 제어", "pages/07_커머스자동화제어센터.py"),
    ]
    for col, item in zip(row1, menu1):
        with col:
            _menu_card(*item)

    row2 = st.columns(4)
    menu2 = [
        ("🔎 통합 상품 소싱", "공급처 상품을 비교하고 판매 후보를 AutoSellerAI 상품으로 가져오는 작업공간", "pages/30_상품소싱.py"),
        ("🖼️ 콘텐츠 스튜디오", "상품 상세페이지용 이미지/콘텐츠를 만들고 기존 상세정보를 보완", "pages/25_AI_상세페이지_제작.py"),
        ("🎨 AI 인물 이미지 스튜디오", "Stable Diffusion WebUI를 이용해 실사 인물·룩북·SNS 이미지를 큐 기반으로 생성", "pages/13_AI_인물_이미지_스튜디오.py"),
        ("🧍 AI 체형 프리셋", "여성 성인 체형 6종을 구조화해 Stable Diffusion 이미지에 적용", "pages/16_AI_체형_프리셋.py"),
    ]
    for col, item in zip(row2, menu2):
        with col:
            _menu_card(*item)

    row3 = st.columns(3)
    menu3 = [
        ("🚀 상품 성장 워크플로우", "상세페이지·Threads 초안·소셜 이미지·Tracking·예약 게시를 상품 단위로 묶어 관리", "pages/14_상품_성장_워크플로우.py"),
        ("🧠 AI Campaign Director", "현재 상품/콘텐츠/성과를 읽고 다음 캠페인 작업 순서와 추천 각도를 자동 기획", "pages/15_AI_캠페인_디렉터.py"),
        ("🧵 마케팅 · Threads", "Threads 콘텐츠 작성·미디어·예약/게시·성과 추적을 관리", "pages/10_Social_Commerce_Threads.py"),
    ]
    for col, item in zip(row3, menu3):
        with col:
            _menu_card(*item)

    # ------------------------------------------------------------------
    # 3. Commerce lifecycle
    # ------------------------------------------------------------------
    st.markdown("## 3. 판매 운영 전체 프로세스")
    _step("① API와 공급처 연결 확인", """
- 쿠팡 / 스마트스토어 API 인증을 먼저 확인합니다.
- 오너클랜·도매꾹·도매매·온채널 등 실제 사용하는 공급처 연결 상태를 확인합니다.
- 연결 오류가 있으면 상품등록·주문수집·발주보다 먼저 해결합니다.
- Seller OS의 시스템 상태와 각 연동 화면에서 오류를 확인합니다.
""")
    _step("② 상품 소싱", """
- **통합 상품 소싱**에서 공급처 상품을 검색합니다.
- 공급가, 배송비, 재고, MOQ, 옵션, 원산지, 이미지 품질을 비교합니다.
- 판매가를 정할 때 플랫폼 수수료·공급처 배송비·반품 위험까지 포함해 실제 이익을 확인합니다.
- 적합한 상품만 AutoSellerAI 상품으로 가져옵니다.
""")
    _step("③ 상품 사실과 판매정보 정리", """
- 상품명, 대표/상세 이미지, 옵션, 원산지, 브랜드, 공급가를 확인합니다.
- 상세페이지가 부족하면 **콘텐츠 스튜디오** 또는 **상품 성장 워크플로우**에서 보완합니다.
- 반복되는 배송비·반품비·판매조건은 통합 판매 운영센터의 템플릿을 사용합니다.
- 실제 상품과 다른 AI 설명이나 이미지를 판매정보로 확정하지 않습니다.
""")
    _step("④ 쿠팡·스마트스토어 등록", """
- Seller OS에서 등록할 상품과 판매채널을 선택합니다.
- 채널마다 카테고리·옵션·필수 속성을 별도로 검증합니다.
- 한 채널의 category ID를 다른 채널에 그대로 복사하지 않습니다.
- 외부 등록은 승인/중복실행 방지 경로를 거쳐 처리합니다.
""")
    _step("⑤ 주문 자동수집", """
- 신규 주문은 스케줄러가 주기적으로 수집합니다.
- 내부 Product / Variant / SupplierOffer와 주문 상품을 매칭합니다.
- 매칭이 확실하지 않으면 자동 발주하지 않고 `오늘 할 일` 또는 관제센터에 예외로 남깁니다.
""")
    _step("⑥ 취소·반품·교환·문의 동기화", """
- 판매채널의 취소·반품·교환 요청을 수집합니다.
- 활성 클레임이 있는 주문은 출고/공급처 발주 전에 HOLD 처리합니다.
- 상품문의·구매자문의는 템플릿 또는 AI 초안을 사용할 수 있지만 외부 답변 전 사실관계를 확인합니다.
""")
    _step("⑦ 발주 직전 안전 검증", """
실제 돈이 나가기 직전에 아래를 다시 확인합니다.

- 주문 취소/클레임/HOLD 여부
- 공급처 재고와 옵션 일치 여부
- 공급가·배송비 변경 여부
- 최소이익·최소마진 정책 충족 여부
- 동일 주문의 기존 발주 여부
- 실제 공급처 Driver가 검증된 실행 경로인지
""")
    _step("⑧ 공급처 발주와 결제", """
- API·예치금·후불 등 자동결제가 가능한 공급처는 검증된 주문 Driver로 처리합니다.
- 카드사 앱 본인승인이 필요한 경우 `사용자 승인 대기`로 전환합니다.
- 사용자는 휴대폰 카드사 앱에서 결제 승인만 수행합니다.
- 카드번호·CVC·카드 비밀번호를 AutoSellerAI에 저장하지 않습니다.
""")
    _step("⑨ 송장 자동수집과 판매채널 반영", """
- 공급처 발주 후 택배사와 송장번호를 추적합니다.
- 송장이 확인되면 판매채널 배송처리 API에 반영합니다.
- idempotency 기록을 사용해 동일 송장을 중복 전송하지 않습니다.
- 지연/누락 주문은 주문·발주 관제센터에서 확인합니다.
""")
    _step("⑩ 안전재고·품절·재입고", """
- 상품별 안전재고와 예약수량 정책을 설정합니다.
- 공급처 재고 미확인을 즉시 0으로 간주하지 않습니다.
- 품절이 충분히 확인된 뒤 판매상태를 변경하고 재입고도 안정적으로 확인된 뒤 판매를 재개합니다.
""")
    _step("⑪ 정산·실제 순이익", """
- 판매채널 정산 데이터를 수집합니다.
- 매출에서 공급가, 플랫폼 수수료, 배송비, 광고비, 반품비, 세금 관련 비용을 반영합니다.
- 예상값과 실제 정산값을 구분하고 실제 데이터가 들어오면 원장을 갱신합니다.
- Seller OS의 수익 화면과 통합 판매 운영센터의 정산 화면에서 확인합니다.
""")

    # ------------------------------------------------------------------
    # 4. Growth workflow
    # ------------------------------------------------------------------
    st.markdown("## 4. 상품 성장 워크플로우 사용법")
    st.markdown("상품 성장 워크플로우는 **하나의 상품 캠페인 안에 상세페이지 → Threads → 이미지 → Tracking → 예약 → 성과**를 묶는 중심 작업공간입니다.")

    _step("① 워크플로우 생성", """
- 성장시킬 `Product`를 선택합니다.
- 목표 판매채널과 destination URL을 지정합니다.
- Campaign Key는 같은 캠페인의 초안·Tracking·게시·주문귀속을 묶는 식별자입니다.
- Threads 각도와 톤은 이후 Campaign Director가 성과 데이터에 따라 추천값을 보정할 수 있습니다.
""")
    _step("② 상세페이지 자산 준비", """
- 기존 상품 상세이미지를 그대로 사용할 수 있습니다.
- 새 상세 이미지를 URL로 등록해 상품 상세페이지에 적용할 수 있습니다.
- reference 기반 유료 AI 상세이미지 생성은 자동으로 실행되지 않으며 별도 허용이 필요합니다.
""")
    _step("③ Threads 초안 준비", """
- 상품 사실과 선택한 콘텐츠 각도를 기준으로 여러 초안을 준비합니다.
- Tracking Link가 있으면 초안과 캠페인을 연결합니다.
- AI 콘텐츠 사용은 비용 가능 작업이므로 Campaign Director에서 별도 허용할 수 있습니다.
""")
    _step("④ 소셜 비주얼 연결", """
- 상품 대표이미지, 상세이미지, Stable Diffusion 완료 이미지를 소셜 비주얼로 사용할 수 있습니다.
- Threads IMAGE 게시에 사용하는 URL은 외부에서 접근 가능한 공개 HTTP(S) 주소여야 합니다.
- Stable Diffusion 결과는 먼저 생성 완료 후 워크플로우에 연결하고 Threads용 공개 미디어로 staging합니다.
""")
    _step("⑤ Tracking과 주문귀속", """
- destination URL이 있으면 Tracking Link를 생성합니다.
- 게시물 클릭 → 주문귀속 → 매출/순이익까지 Campaign Key로 연결됩니다.
- 이 데이터는 이후 Content Profit Feedback과 Campaign Director의 다음 추천에 사용됩니다.
""")

    # ------------------------------------------------------------------
    # 5. Campaign Director
    # ------------------------------------------------------------------
    st.markdown("## 5. 🧠 AI Campaign Director")
    st.caption("Campaign Director는 새 게시 엔진이 아니라 기존 상품 성장 워크플로우 위에서 다음 행동을 결정하는 기획·오케스트레이션 계층입니다.")

    st.markdown("### Director가 보는 정보")
    st.markdown("""
- 상품 사실과 원본 이미지
- 상세페이지 준비 상태
- Threads 초안 상태
- 현재 소셜 이미지
- Tracking Link 상태
- 예약/게시 상태
- 클릭·주문귀속·순이익
- 상품별 `ContentStrategyProfile`의 preferred/avoid angle과 winning pattern
""")

    st.markdown("### 권장 사용 순서")
    st.markdown("""
1. **상품 성장 워크플로우**를 먼저 만듭니다.  
2. **AI Campaign Director → Plan 생성**을 누릅니다. Plan은 부작용 없는 로컬 기획입니다.  
3. 추천 콘텐츠 각도, 초안 개수, 상세 장면 수, 소셜 비주얼, 게시 탐색 시간대, 경고를 확인합니다.  
4. AI 카피가 필요할 때만 **AI 콘텐츠 허용**을 켭니다.  
5. 유료 reference 상세이미지가 필요할 때만 **유료 상세이미지 허용**을 켭니다.  
6. 준비된 자산을 확인한 뒤 별도 예약 단계에서 초안·시각·미디어를 선택합니다.  
7. 게시 후 클릭·주문·수익이 쌓이면 다음 Plan이 실제 성과를 반영합니다.
""")

    tier_cols = st.columns(4)
    tier_data = [
        ("local", "무료 로컬/DB 작업", "상품 사실 확인, Tracking 준비, 기존 자산 재사용"),
        ("ai_compute", "AI 콘텐츠 계산", "Threads 카피 생성. `allow_ai_content=true` 필요"),
        ("ai_cost", "비용 가능한 AI 생성", "reference 상세이미지. `allow_paid_detail_generation=true` 필요"),
        ("external_publish", "외부 상태 변경", "예약/게시. Prepare에서는 실행하지 않고 별도 schedule 단계 사용"),
    ]
    for col, (name, label, desc) in zip(tier_cols, tier_data):
        with col:
            with st.container(border=True):
                st.markdown(f"#### `{name}`")
                st.write(label)
                st.caption(desc)

    st.warning("**중요:** `Prepare`는 외부 Threads 게시를 몰래 실행하지 않습니다. 예약 시점에도 준비된 초안/자산만 사용하며 새 AI 카피나 이미지를 숨겨서 생성하지 않습니다.")

    # ------------------------------------------------------------------
    # 6. Stable Diffusion
    # ------------------------------------------------------------------
    st.markdown("## 6. 🎨 AI 인물 이미지 스튜디오")
    st.markdown("AutoSellerAI는 AUTOMATIC1111 Stable Diffusion WebUI를 이미지 생성 엔진으로 사용하고, 프롬프트·큐·결과·재생성 이력은 AutoSellerAI에서 관리합니다.")

    _step("① Stable Diffusion WebUI 실행", """
`webui-user.bat`의 기존 옵션을 유지하면서 아래 옵션을 추가합니다.

```bat
set COMMANDLINE_ARGS=--api --listen --port 7860
```

- `--api`: AutoSellerAI가 REST API를 호출할 수 있게 합니다.
- `--listen`: Docker 컨테이너가 Windows 호스트 WebUI에 접근할 수 있게 합니다.
- AutoSellerAI Docker 내부에서는 `http://host.docker.internal:7860`을 사용합니다.
- `--listen` 사용 시 Windows Firewall의 불필요한 Public 네트워크 허용은 피합니다.
""")
    _step("② 생성 환경 확인", """
이미지 스튜디오 상단에서 다음이 모두 정상인지 확인합니다.

- Stable Diffusion WebUI 연결됨
- Image Worker 1개 이상
- 현재 체크포인트 확인
- ADetailer 설치 시 사용 가능 표시

WebUI와 image-worker가 모두 준비되어야 생성 버튼이 활성화됩니다.
""")
    _step("③ 인물 설정", """
- 얼굴·헤어, 체형, 의상·분위기, 촬영 탭에서 구조화 옵션을 선택합니다.
- 목적 프리셋은 촬영·해상도·Steps·CFG를 빠르게 맞추는 용도입니다.
- 직접 Positive/Negative Prompt는 구조화 옵션으로 표현하기 어려운 소품·연출만 추가하는 것을 권장합니다.
""")
    _step("④ 고급 설정", """
- Sampler / Scheduler / Checkpoint / Steps / CFG / Seed를 조정할 수 있습니다.
- Hires.fix는 최종 해상도를 높이지만 VRAM 사용량도 증가합니다.
- ADetailer가 감지된 경우 얼굴 보정 payload가 자동 추가됩니다.
- 체크포인트 선택은 요청 단위 override이므로 생성 후 WebUI의 전역 체크포인트를 원래대로 복원합니다.
""")
    _step("⑤ 생성 이력과 재사용", """
- 모든 생성은 전용 `image` RQ worker에 등록됩니다.
- 생성 이력에서 PNG, Prompt, Payload, Seed, 응답 메타데이터를 확인할 수 있습니다.
- `같은 Seed 재생성`은 구도를 재현할 때 사용하고, `랜덤 Seed 재생성`은 같은 설정의 다른 변형을 만들 때 사용합니다.
""")

    # ------------------------------------------------------------------
    # 7. Body profiles
    # ------------------------------------------------------------------
    st.markdown("## 7. 🧍 AI 체형 프리셋")
    st.markdown("여성 성인 인물 생성에는 아래 6개 대표 체형을 사용할 수 있습니다.")
    st.markdown("**매우 슬림 · 슬림 · 슬림 글래머 · 균형형 · 볼륨형 · 운동형**")

    st.markdown("### 구조화되는 세부 축")
    st.markdown("""
- 전체 체형
- 키 인상
- 어깨선
- 흉곽
- 상체 볼륨
- 상체 비율
- 허리·힙 실루엣
- 근육·복부 톤
- 다리 비율 인상
""")

    st.markdown("### 체형 참고표의 숫자는 어떻게 쓰이나요?")
    st.markdown("""
키·체중·BMI·체지방률·밑가슴·WHR·브라 사이즈와 의상 착용 시 인상은 **참고 메타데이터**로 보존합니다.  
Stable Diffusion은 cm/kg/BMI를 정확히 계산하지 못하므로 실제 Prompt에는 숫자를 강제로 넣지 않습니다.

대신 다음처럼 시각적 자연어로 변환합니다.

- `narrow ribcage`
- `balanced natural proportions`
- `defined waist`
- `realistic clothing drape`
- `toned athletic core`
""")
    st.info("여성 체형 프리셋은 여성 생성에만 세부 적용됩니다. 남성 생성에는 여성용 bust/feminine 체형 묘사가 섞이지 않도록 분리되어 있습니다.")
    st.warning("모든 기본 체형 프리셋은 **성인·완전 착의 상업/라이프스타일 이미지**를 전제로 합니다. 슬림 글래머/볼륨형은 과장된 해부학을, 운동형은 bodybuilder 수준의 과도한 근육을 자동 억제합니다.")

    # ------------------------------------------------------------------
    # 8. Threads and performance loop
    # ------------------------------------------------------------------
    st.markdown("## 8. 🧵 Threads 콘텐츠 → Tracking → 수익학습")
    _step("① 콘텐츠 초안", """
- 상품 사실을 기반으로 문제해결형·비교형·라이프스타일형 등 콘텐츠 각도를 선택합니다.
- Campaign Director가 과거 성과가 있으면 preferred angle을 우선 추천하고 손실/저성과 각도는 피하도록 안내합니다.
""")
    _step("② 이미지 연결", """
- 상품 이미지, 상세 이미지, Stable Diffusion 생성 이미지를 사용할 수 있습니다.
- Threads API에서 사용하는 이미지 URL은 외부에서 접근 가능해야 합니다.
""")
    _step("③ Tracking Link", """
- Tracking Link를 통해 게시물 클릭을 캠페인/상품과 연결합니다.
- destination URL 또는 PUBLIC_BASE_URL이 외부에서 접근 불가능하면 Tracking/미디어 게시 준비 상태가 제한될 수 있습니다.
""")
    _step("④ 주문 귀속과 수익 피드백", """
- 클릭 이후 주문이 연결되면 deterministic/추정 귀속을 기록합니다.
- 매출뿐 아니라 공급가·플랫폼 수수료·배송비·광고비·반품비 등을 반영해 순이익을 계산합니다.
- 클릭, 전환율, 순이익, attribution confidence, 반품 품질을 종합한 Content Score가 다음 캠페인 학습에 사용됩니다.
""")

    # ------------------------------------------------------------------
    # 9. Daily operations
    # ------------------------------------------------------------------
    st.markdown("## 9. 하루 운영 순서")
    st.markdown("""
1. **Seller OS → 오늘 할 일**에서 사람 판단이 필요한 예외 확인  
2. **주문·발주 관제센터**에서 카드승인 대기, 발주실패, 송장지연 확인  
3. **통합 판매 운영센터**에서 클레임·CS·재고위험·정산 확인  
4. **커머스 자동화 제어센터**에서 수집/스케줄러/worker 상태 확인  
5. **Seller OS → 수익**에서 실제 정산과 순이익 확인  
6. 성장시킬 상품이 있으면 **상품 성장 워크플로우 → AI Campaign Director** 실행  
7. 필요한 경우에만 **AI 인물 이미지/체형 프리셋/콘텐츠 스튜디오** 사용  
8. 게시 후 Tracking·주문귀속·수익 피드백이 정상 쌓이는지 확인
""")

    # ------------------------------------------------------------------
    # 10. Human approvals
    # ------------------------------------------------------------------
    st.markdown("## 10. 사용자가 직접 확인해야 하는 작업")
    st.markdown("""
자동화 이후에도 다음은 사람 확인 또는 명시적 허용이 필요할 수 있습니다.

- 카드사 앱 본인승인
- 공급가 급등으로 마진이 깨진 주문
- 품절·옵션 불일치·주소 오류
- 취소·반품·교환의 예외 판단
- AI가 확신할 수 없는 상품/주문 매칭
- 고객에게 법적·정책적 의미가 큰 답변
- AI 카피/API 비용을 발생시킬 수 있는 작업
- 유료 reference 상세이미지 생성
- Threads 예약/외부 게시
""")

    # ------------------------------------------------------------------
    # 11. Runtime and workers
    # ------------------------------------------------------------------
    st.markdown("## 11. 자동화 · Queue · Worker 이해하기")
    st.markdown("""
- 일반 동기화/판매 자동화 작업은 RQ worker를 사용합니다.
- 실제 외부 주문처럼 위험도가 높은 작업은 별도 승인과 검증을 거칩니다.
- Stable Diffusion과 상세이미지 생성은 전용 `image` queue/worker를 사용합니다.
- 같은 작업이 반복 큐잉되지 않도록 dedupe/idempotency 상태를 확인합니다.
- `queued` → `started/running` → `completed/failed` 흐름으로 상태를 확인합니다.
""")

    st.code(
        "docker compose ps\n"
        "docker compose logs --tail=100 autoseller\n"
        "docker compose logs --tail=100 seller-api\n"
        "docker compose logs --tail=100 image-worker",
        language="powershell",
    )

    # ------------------------------------------------------------------
    # 12. Error handling
    # ------------------------------------------------------------------
    st.markdown("## 12. 오류가 쌓였을 때")
    st.markdown("""
- `오늘 할 일 → 오류 데이터 초기화`: 오류 메시지/실패 기록을 정리합니다. 실제 주문을 성공 처리하는 기능이 아닙니다.
- `설정·자동화 → 전체 데이터 초기화`: 개발/테스트 데이터를 완전히 다시 시작할 때만 사용합니다.
- 전체 초기화는 실행 중 작업이 없어야 하며 확인문구 `RESET_ALL_DATA`를 직접 입력해야 합니다.
- `.env`와 소스코드는 전체 데이터 초기화 대상이 아닙니다.
- 이미지 생성 실패는 WebUI 연결, image-worker, checkpoint/VRAM, ADetailer 설치 여부 순으로 확인합니다.
- Threads 이미지 게시 실패는 먼저 media URL이 외부에서 접근 가능한지 확인합니다.
""")

    # ------------------------------------------------------------------
    # 13. Stable Diffusion troubleshooting
    # ------------------------------------------------------------------
    st.markdown("## 13. Stable Diffusion 연결 문제 해결")
    troubleshoot_tabs = st.tabs(["WebUI 연결 안 됨", "Image Worker 없음", "VRAM/생성 실패", "Threads 이미지 URL"])
    with troubleshoot_tabs[0]:
        st.markdown("""
1. Windows에서 WebUI가 실제로 실행 중인지 확인합니다.  
2. `http://127.0.0.1:7860`이 열리는지 확인합니다.  
3. `http://127.0.0.1:7860/docs`가 열리는지 확인합니다.  
4. `webui-user.bat`에 `--api --listen --port 7860`이 포함되어 있는지 확인합니다.  
5. Docker 설정의 `SD_WEBUI_DOCKER_URL`은 기본적으로 `http://host.docker.internal:7860`을 사용합니다.
""")
    with troubleshoot_tabs[1]:
        st.code("docker compose up -d image-worker\ndocker compose ps", language="powershell")
        st.caption("이미지 스튜디오 상단에 Image Worker가 1개 이상 표시되어야 합니다.")
    with troubleshoot_tabs[2]:
        st.markdown("""
- 기본 해상도 또는 Hires 배율을 낮춥니다.
- Batch Size를 줄입니다.
- 너무 높은 Steps를 줄입니다.
- 체크포인트가 현재 GPU VRAM에 맞는지 확인합니다.
- ADetailer/Hires.fix를 하나씩 꺼서 어느 단계에서 실패하는지 분리합니다.
""")
    with troubleshoot_tabs[3]:
        st.markdown("""
Threads IMAGE 게시용 URL은 `localhost`, `127.0.0.1`, 사설 `.local` 주소가 아니라 Meta 서버가 접근 가능한 공개 HTTPS 주소여야 합니다.  
Tracking Link를 게시물 본문에 넣으려면 `PUBLIC_BASE_URL`도 공개 접근 가능해야 합니다.
""")

    # ------------------------------------------------------------------
    # 14. REST quick reference
    # ------------------------------------------------------------------
    st.markdown("## 14. 운영/개발자용 REST 빠른 참고")
    st.caption("일반 사용자는 UI만 사용해도 됩니다. 아래는 문제 확인이나 별도 클라이언트 연동 시 참고합니다.")
    st.code(
        "# Seller OS API base\n"
        "/api/v3\n\n"
        "# Stable Diffusion Image Studio\n"
        "GET  /api/v3/image-studio/health\n"
        "GET  /api/v3/image-studio/catalog\n"
        "GET  /api/v3/image-studio/body-profiles\n"
        "POST /api/v3/image-studio/preview\n"
        "POST /api/v3/image-studio/generations\n\n"
        "# Campaign Director\n"
        "GET  /api/v3/product-growth/workflows/{id}/director\n"
        "POST /api/v3/product-growth/workflows/{id}/director/plan\n"
        "POST /api/v3/product-growth/workflows/{id}/director/prepare\n"
        "POST /api/v3/product-growth/workflows/{id}/director/schedule",
        language="text",
    )
    st.caption("비로컬 환경에서 Seller OS control API를 사용할 때는 `SELLER_API_TOKEN` 정책을 따릅니다.")

    # ------------------------------------------------------------------
    # 15. Backup/safety checklist
    # ------------------------------------------------------------------
    st.markdown("## 15. 업데이트 전·후 체크리스트")
    st.markdown("""
**업데이트 전**
- 실행 중인 위험 작업/발주가 없는지 확인
- `.env`와 `data/` 백업
- Stable Diffusion 생성 중인 작업이 없는지 확인

**업데이트 후**
- `docker compose ps`에서 서비스 상태 확인
- Seller OS 접속 확인
- Seller API / Social API 상태 확인
- Redis/worker 확인
- Stable Diffusion을 쓰는 경우 WebUI + image-worker 확인
- 테스트 상품 1개로 Tracking/초안/이미지/예약 흐름을 점검
""")

    st.success(
        "**권장 운영 방식:** 평소에는 Seller OS에서 예외와 수익만 관리하고, 성장시킬 상품이 생겼을 때 "
        "`상품 성장 워크플로우 → AI Campaign Director → 필요한 콘텐츠/이미지 생성 → 예약 게시 → Tracking/수익학습` 순서로 사용하면 됩니다."
    )
