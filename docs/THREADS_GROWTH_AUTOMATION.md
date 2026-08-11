# Threads Growth Automation

AutoSellerAI의 Threads Social Commerce 위에 다음 폐쇄형 루프를 추가한다.

```text
Product DB
  -> AI Content Engine
  -> SocialContentDraft
  -> TrackingLink
  -> ScheduledSocialPost
  -> Threads publish
  -> TrackingClick
  -> Naver/Coupang PlatformOrder
  -> OrderAttribution
  -> campaign revenue/confidence
```

## 1. AI 콘텐츠 자동 생성

`app/social/threads/content_engine.py`

- 문제해결형 / 경험형 / 질문형 / 비교형 / 리스트형
- Claude API가 있으면 상품 DB를 context로 후보 생성
- API가 없거나 실패하면 안전한 규칙 기반 fallback
- 500자 제한
- DB에 없는 성능/배송일/할인/최저가를 임의 생성하지 않도록 prompt 제한
- `social_content_drafts`에 후보, CTA, score, 판매처, 상품 URL을 저장

API:

`POST /api/v1/threads/content/generate`

## 2. Tracking URL

`app/social/threads/tracking.py`

원래 상품 URL 대신 다음 URL을 SNS 유입용으로 사용한다.

```text
https://PUBLIC_BASE_URL/t/{code}
```

동작:

```text
GET /t/{code}
 -> link lookup
 -> click_id 생성
 -> IP 원문 미저장, salted SHA-256 hash 저장
 -> user-agent/referer 기록
 -> 실제 SmartStore/Coupang URL로 302 redirect
```

환경변수:

```text
PUBLIC_BASE_URL=https://seller.example.com
TRACKING_HASH_SALT=<long-random-secret>
```

주의: `PUBLIC_BASE_URL`은 Meta/사용자 브라우저에서 접근 가능한 HTTPS 공개 주소여야 한다.

## 3. 예약 게시

`scheduled_social_posts`에 UTC 기준 예약시간을 저장한다. GUI에서는 Asia/Seoul(KST)로 입력/표시한다.

Docker 서비스:

```text
threads-scheduler
```

명령:

```bash
python -m app.social.threads.scheduling
```

기본 20초 간격으로 due schedule을 확인한다.

```text
scheduled -> publishing -> published
                         -> failed
```

성공 시 기존 `threads_posts`에도 실제 Threads post ID를 기록하고 TrackingLink와 게시물 관계를 연결한다.

## 4. 실제 주문 Attribution

실제 주문 원천은 AutoSellerAI의 기존 `platform_orders` 테이블이다.

- SmartStore 주문은 네이버 Commerce API에서 수집한 실제 주문
- Coupang 주문은 Wing Open API에서 수집한 실제 주문

외부 마켓 주문 API가 AutoSellerAI의 `click_id`를 주문 응답에 돌려주지는 않으므로 자동 귀속은 기본적으로 확률적이다.

현재 Attribution 조건:

1. `PlatformOrder.product_id` 일치
2. `TrackingLink.product_id` 일치
3. 플랫폼 일치 (`smartstore` / `coupang`)
4. 클릭 시각 <= 주문 시각
5. 지정 lookback window 안의 클릭
6. 가장 최근 클릭 우선
7. 경쟁 캠페인이 많으면 confidence 감소

기본 신뢰도:

- 1시간 이내: 0.92
- 6시간 이내: 0.86
- 24시간 이내: 0.76
- 그 이후 lookback 내: 0.62

여러 TrackingLink가 경쟁하면 추가 감점한다.

결과 타입:

```text
probabilistic  자동 추정 귀속
deterministic 운영자 검토 후 확정 귀속
unattributed   귀속 근거 없음
```

GUI에서 운영자가 probabilistic 결과를 확인한 뒤 deterministic으로 승격할 수 있다.

환경변수:

```text
ATTRIBUTION_WINDOW_HOURS=72
ATTRIBUTION_AUTO_ENABLED=true
ATTRIBUTION_RUN_INTERVAL_SECONDS=300
```

`threads-scheduler`가 예약 발행과 별개로 기본 5분마다 새 `PlatformOrder`를 Attribution한다.

API:

```text
POST /api/v1/attribution/run
GET  /api/v1/attribution
```

## 5. Streamlit GUI

`gui/pages/11_Threads_Growth_Automation.py`

탭:

1. AI 콘텐츠 자동 생성
2. Tracking URL
3. 게시 예약
4. 구매 Attribution

KPI:

- 콘텐츠 초안 수
- 예약 대기 수
- Tracking 클릭 수
- 귀속 주문 수
- 귀속 매출
- 평균 Attribution confidence

## 6. 운영 전 필수

1. `.env`에 Threads 토큰 설정
2. `PUBLIC_BASE_URL`을 실제 HTTPS 도메인으로 지정
3. `TRACKING_HASH_SALT` 변경
4. 네이버/쿠팡 주문 수집이 `platform_orders.product_id`를 정상 연결하는지 확인
5. `docker compose up --build`
6. 처음에는 Attribution 결과를 운영자가 검수

## 7. 정확도 한계와 다음 단계

현재 구조에서 SmartStore/Coupang은 외부 SNS click ID를 주문에 직접 전달하지 않기 때문에, 자동 귀속은 분석 모델이다. 실제 주문 자체는 실데이터지만 어느 SNS 클릭이 그 주문을 만들었는지는 확률적으로 연결한다.

정확도를 높이는 다음 단계:

- 상품별 클릭 직후 주문 전환율 학습
- 캠페인별 baseline 비교
- 플랫폼별 lookback window 학습
- 반복 클릭/봇 필터링
- 주문 취소/반품 발생 시 귀속 매출 차감
- UTM/마켓이 허용하는 캠페인 파라미터가 있을 경우 추가 활용
- PostgreSQL 전환 후 동시성/분석 쿼리 강화
