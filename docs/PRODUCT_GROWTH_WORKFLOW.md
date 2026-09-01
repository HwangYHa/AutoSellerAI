# 상품 상세페이지 · Threads 통합 성장 워크플로우

## 목표

한 상품의 상세페이지 제작과 Threads 마케팅을 서로 독립된 작업으로 관리하지 않고 `product_id + campaign_key`를 공통 축으로 묶습니다.

```text
Product
  ↓
상품 사실 / 원본 이미지
  ├─→ 상세페이지 자산 ─→ Product.detail_images / detail_html
  │
  └─→ Threads 카피 초안
          ↓
      소셜 비주얼
      ├─ 실제 상품 이미지
      ├─ 상세페이지 이미지 재사용
      └─ Stable Diffusion 라이프스타일 이미지
          ↓
      Tracking Link
          ↓
      ScheduledSocialPost
          ↓
      ThreadsPost
          ↓
      TrackingClick → OrderAttribution → 수익 피드백
```

## 핵심 원칙

### 1. 상품 정체성은 Product가 기준

상품명, 카테고리, 브랜드, 소재, 가격, 공급처 이미지와 상세이미지가 상업 콘텐츠의 사실 기준입니다. 확인되지 않은 기능이나 성능을 마케팅 카피 또는 이미지 프롬프트에서 추가하지 않습니다.

### 2. 상세페이지와 Stable Diffusion의 역할을 분리

상세페이지에서 상품 외형 보존이 필요한 이미지는 기존 `app.media.ai_detail_page`의 reference 기반 GPT Image 흐름을 사용합니다. Stable Diffusion txt2img 결과는 가상 인플루언서, 분위기, 라이프스타일 등 Threads 소셜 비주얼에만 사용하며 정확한 상품 로고·패턴·구성품의 근거로 취급하지 않습니다.

### 3. 유료 상세 이미지 생성은 비동기

`POST /api/v3/product-growth/workflows/{id}/detail-generation`은 이미지 생성을 HTTP 요청 안에서 직접 수행하지 않습니다. 기존 Redis `image` 큐에 등록하고 `image-worker`가 실행합니다. 동일 workflow에서 이미 queued/running인 상세 이미지 Job이 있으면 재사용합니다.

### 4. Threads는 즉시 게시하지 않음

통합 워크플로우는 `ScheduledSocialPost`까지만 생성합니다. 실제 외부 게시는 기존 `threads-scheduler`가 담당합니다. 같은 workflow/draft에 이미 scheduled/publishing/published 레코드가 있으면 같은 예약을 다시 만들지 않습니다.

### 5. 클릭·주문 추적은 공개 URL일 때만 게시

TrackingLink 자체는 미리 만들 수 있지만 Threads 게시문에 추적 URL을 넣으려면 `PUBLIC_BASE_URL`이 인터넷에서 접근 가능한 HTTP(S) 주소여야 합니다. localhost/127.0.0.1/.local 주소는 게시용 Tracking Link로 인정하지 않습니다.

## 워크플로우 상태

동적 상태는 실제 하위 레코드를 기준으로 계산합니다.

- `draft`: 캠페인만 생성됨
- `content_ready`: Threads 초안 생성됨
- `ready_to_schedule`: 초안 + Tracking Link 준비
- `scheduled`: 예약 게시 존재
- `published`: Threads 게시 완료
- `partial_failed`: 워크플로우 작업 오류 존재

상세페이지 준비 여부, 소셜 이미지 준비 여부, 게시/주문귀속 성과는 상태와 별도로 함께 노출됩니다.

## Seller OS REST API

기본 prefix:

```text
/api/v3/product-growth
```

주요 endpoint:

```text
GET  /catalog
POST /workflows
GET  /workflows
GET  /workflows/{id}
POST /workflows/{id}/tracking
POST /workflows/{id}/threads-drafts
POST /workflows/{id}/detail-assets
POST /workflows/{id}/detail-assets/apply
POST /workflows/{id}/detail-generation
POST /workflows/{id}/social-visual/attach
POST /workflows/{id}/social-visual/stage
POST /workflows/{id}/social-visual/product
POST /workflows/{id}/schedules
```

Seller OS API의 기존 `SELLER_API_TOKEN` Bearer 인증 정책을 그대로 상속합니다.

## UI

Streamlit 사이드바의 **상품 성장 워크플로우**에서 다음 작업을 한 화면에서 수행합니다.

1. 상품 선택 및 캠페인 생성
2. 현재 상세페이지 자산 확인
3. 명시적 유료 상세 이미지 생성 큐 등록
4. Threads 카피 초안 생성
5. 실제 상품 이미지 또는 Stable Diffusion 소셜 비주얼 연결
6. Tracking Link 상태 확인
7. KST 기준 Threads 예약 게시
8. 게시 수, 귀속 주문, 귀속 매출 확인

## Docker 데이터 흐름

`autoseller`, `seller-api`, `image-worker`, `social-api`, `threads-scheduler`가 모두 `./data:/app/data` 볼륨을 공유합니다. 따라서 Stable Diffusion PNG를 `data/threads_media`에 스테이징하면 social-api가 `/media/threads/...`로 같은 파일을 제공할 수 있습니다.

Meta가 이미지를 가져가려면 `PUBLIC_BASE_URL` 또는 `THREADS_MEDIA_PUBLIC_BASE_URL`이 외부에서 접근 가능한 HTTPS 주소여야 합니다.

## 운영 순서 권장

```text
1. 상품 사실/원본 이미지 확인
2. 상세페이지 준비
3. 통합 캠페인 생성
4. Threads 초안 생성
5. 소셜 비주얼 선택
6. 공개 Tracking/Media URL 확인
7. 예약 게시
8. threads-scheduler 게시
9. 클릭/주문 귀속
10. 수익 피드백을 다음 콘텐츠 생성에 반영
```
