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
    |
    +--> Claude Agent (복잡한 자연어 문의)
    |
    +--> SQLite (상품 + Threads 이벤트/리드/답글)
    |
    +--> Threads API reply

Streamlit :8501  ----> same SQLite DB
      |
      +--> Social Commerce / Threads page
```

## Streamlit Control Center

`gui/pages/10_Social_Commerce_Threads.py`를 추가했다. Streamlit 멀티페이지 네비게이션에서 Social Commerce / Threads 관리 화면으로 진입할 수 있다.

관리 화면은 다음 7개 탭으로 구성된다.

1. `Dashboard`
   - 게시물, 댓글, AI 초안, 발행 답글, HOT Lead, 사람 확인 건수
   - 평균 구매의도, 활성 Rule, 검수/발행 대기 현황
   - 최근 댓글과 운영 체크
2. `게시물`
   - 기존 AutoSellerAI 상품과 Threads 게시물 연결
   - Campaign Key / CTA 키워드 지정
   - Threads 실게시 및 게시 이력 조회
3. `댓글`
   - Intent / 구매의도 / 사람 확인 여부 필터
   - 댓글 처리 상태 확인
4. `HOT Leads`
   - 구매의도 점수 기준 Lead 우선순위화
   - HOT / WARM 등급 시각화
5. `자동화 Rule`
   - 댓글 키워드 → 고정 답글 Rule 생성
   - 특정 상품 또는 전체 상품 범위 지정
   - 우선순위, ON/OFF, 삭제
6. `AI Sales Inbox`
   - Rule/AI 답변 초안 검수
   - 민감 문의 Human Review 표시
   - 초안 수정/저장
   - 승인 후 Threads 공개 답글 발행
7. `Threads 설정`
   - Threads / Webhook / Redis 환경변수 연결 상태
   - 자동답글 운영 모드
   - 필요한 API 권한 안내

## Safety defaults

- `THREADS_AUTO_REPLY=false`가 기본값이다. 초기 운영은 AI가 분류/초안을 만들고 사람이 확인한다.
- 반품/불만은 `requires_human=true`로 강제하여 자동 공개 답글을 보내지 않는다.
- 상품 사양은 기존 `products` 테이블의 데이터만 Context로 제공한다.
- Webhook POST는 `X-Hub-Signature-256` HMAC 검증을 지원한다.
- Access Token/Secret은 코드나 DB에 넣지 않고 환경변수에서 읽는다.
- 동일 comment ID는 DB unique key로 중복 처리하지 않는다.
- Webhook 요청에서 AI/Threads API를 직접 호출하지 않고 Redis Queue로 넘긴 뒤 즉시 응답한다.

## Environment

```bash
cp .env.example .env
```

필수 설정:

```text
THREADS_USER_ID
THREADS_ACCESS_TOKEN
THREADS_APP_SECRET
THREADS_VERIFY_TOKEN
```

실제 자동 답글을 켤 때만:

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

Streamlit 좌측 멀티페이지 네비게이션에서 `Social Commerce Threads` 페이지로 이동한다.

## API

### Threads Webhook verification

`GET /api/v1/threads/webhook`

Meta의 `hub.mode`, `hub.verify_token`, `hub.challenge` 파라미터를 처리한다.

### Threads Webhook receiver

`POST /api/v1/threads/webhook`

이벤트를 검증한 뒤 RQ `threads` queue에 적재한다.

### Publish

`POST /api/v1/threads/posts`

```json
{
  "text": "차량 청소할 때 시트 사이가 제일 귀찮더라고요. 궁금하면 청소기라고 남겨주세요.",
  "product_id": 381,
  "campaign_key": "car-cleaning-202608",
  "cta_keyword": "청소기"
}
```

### Automation rule

`POST /api/v1/threads/rules`

```json
{
  "keyword": "청소기",
  "reply_template": "말씀드린 제품 정보는 판매 페이지에서 확인하실 수 있어요.",
  "product_id": 381,
  "priority": 10,
  "enabled": true
}
```

### Sales Inbox data

- `GET /api/v1/threads/comments`
- `GET /api/v1/threads/leads?min_score=0.7`

## Data model

- `threads_posts`: Threads 게시물과 내부 상품 연결
- `threads_comments`: 댓글, intent, 구매의도 점수, 사람 개입 여부
- `threads_replies`: AI/규칙/사람 답글 및 발행 상태
- `threads_automation_rules`: 키워드 CTA 규칙

## Processing policy

```text
Webhook
  -> idempotency check
  -> post/product context
  -> keyword rule first
  -> rule intent classifier
  -> Claude only when useful
  -> policy filter
  -> human_review OR Threads API reply
```

키워드 CTA처럼 확정적인 댓글은 규칙 엔진이 처리한다. 반품/불만은 사람이 처리한다. 그 외 자연어 상품문의는 Claude가 기존 상품 DB 범위 안에서 답변 초안을 만든다.

## Next implementation priorities

1. Meta OAuth + 장기 토큰 갱신/만료일 관리
2. 이미지/영상 게시 + 예약 게시
3. Content AI 상품선정/게시물 초안 생성
4. tracking redirect + 네이버/쿠팡 주문 attribution
5. 게시물별 매출/마진 기반 Content Score 학습
6. SQLite -> PostgreSQL 전환 및 Alembic 도입
