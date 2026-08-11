# Threads AI Sales Architecture

AutoSellerAI의 기존 Streamlit/SQLite 애플리케이션을 유지하면서 Threads를 소셜 커머스 유입 채널로 추가한다.

## Runtime

```text
Threads / Meta
    |
    | webhook
    v
FastAPI social-api :8000
    |
    | enqueue
    v
Redis + RQ
    |
    v
threads-worker
    |
    +--> Rule Engine (키워드/가격/배송/재고)
    +--> Claude Agent (복잡한 자연어 문의)
    +--> SQLite (상품 + Threads 이벤트/리드/답글)
    +--> Threads API reply

threads-scheduler
    +--> 예약 게시 발행
    +--> 신규 PlatformOrder Attribution 주기 실행

Streamlit :8501
    +--> Social Commerce / Threads
    +--> Threads Growth Automation
```

## Streamlit Control Center

`gui/pages/10_Social_Commerce_Threads.py`

1. Dashboard
2. 게시물
3. 댓글
4. HOT Leads
5. 자동화 Rule
6. AI Sales Inbox
7. Threads 설정

`gui/pages/11_Threads_Growth_Automation.py`

1. AI 콘텐츠 자동 생성
2. Tracking URL
3. 게시 예약
4. 네이버·쿠팡 구매 Attribution

## Safety defaults

- `THREADS_AUTO_REPLY=false`가 기본값이다.
- 반품/불만은 `requires_human=true`로 강제한다.
- 상품 사양은 기존 `products` 테이블의 데이터만 Context로 제공한다.
- Webhook POST는 `X-Hub-Signature-256` HMAC 검증을 지원한다.
- Access Token/Secret은 환경변수에서 읽는다.
- Webhook 요청에서 AI/Threads API를 직접 호출하지 않고 Redis Queue로 넘긴다.
- Tracking 클릭 IP 원문은 저장하지 않고 salted SHA-256 hash만 저장한다.

## Environment

```bash
cp .env.example .env
```

필수 Threads 설정:

```text
THREADS_USER_ID
THREADS_ACCESS_TOKEN
THREADS_APP_SECRET
THREADS_VERIFY_TOKEN
```

Growth Automation 설정:

```text
PUBLIC_BASE_URL=https://seller.example.com
TRACKING_HASH_SALT=<long-random-secret>
ATTRIBUTION_WINDOW_HOURS=72
ATTRIBUTION_AUTO_ENABLED=true
ATTRIBUTION_RUN_INTERVAL_SECONDS=300
```

실제 자동 댓글을 켤 때만:

```text
THREADS_AUTO_REPLY=true
```

## Start

```bash
docker compose up --build
```

- Seller GUI: `http://localhost:8501`
- Social API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

## Threads API

### Webhook verification

`GET /api/v1/threads/webhook`

### Webhook receiver

`POST /api/v1/threads/webhook`

### Publish

`POST /api/v1/threads/posts`

### Automation rule

`POST /api/v1/threads/rules`

### Sales Inbox

- `GET /api/v1/threads/comments`
- `GET /api/v1/threads/leads?min_score=0.7`

## Growth Automation API

### AI Content

`POST /api/v1/threads/content/generate`

상품 DB 기반으로 Threads 후보 콘텐츠를 생성하고 `social_content_drafts`에 저장한다.

### Tracking URL

`POST /api/v1/threads/tracking-links`

공개 URL:

```text
GET /t/{code}
```

클릭 기록 후 실제 SmartStore/Coupang URL로 302 redirect한다.

### Schedule

```text
POST /api/v1/threads/schedules
GET  /api/v1/threads/schedules
```

DB에는 UTC로 저장하고 GUI에서는 KST로 변환한다.

### Attribution

```text
POST /api/v1/attribution/run
GET  /api/v1/attribution
```

실제 주문 원천은 기존 `platform_orders` 테이블이다. 외부 마켓 주문 API는 AutoSellerAI의 click_id를 반환하지 않으므로 자동 귀속은 상품·플랫폼·클릭 이후 주문시간을 이용한 probabilistic 방식이다. 운영자가 검증한 결과는 deterministic으로 승격한다.

상세 내용: `docs/THREADS_GROWTH_AUTOMATION.md`

## Core data model

Threads Sales:

- `threads_posts`
- `threads_comments`
- `threads_replies`
- `threads_automation_rules`

Growth:

- `social_content_drafts`
- `scheduled_social_posts`
- `tracking_links`
- `tracking_clicks`
- `order_attributions`

## Closed-loop

```text
상품 DB
 -> AI 콘텐츠
 -> Tracking URL
 -> 예약 게시
 -> Threads
 -> 클릭
 -> SmartStore/Coupang
 -> 실제 PlatformOrder
 -> Attribution confidence
 -> 운영자 확정
 -> 캠페인 매출 데이터
```

## Next implementation priorities

1. Meta OAuth + 장기 토큰 갱신/만료일 관리
2. 이미지/영상 게시
3. 주문 취소/반품 발생 시 Attribution 매출 차감
4. 콘텐츠 성과와 실제 순마진 feedback loop
5. SQLite -> PostgreSQL 전환 및 Alembic 도입
