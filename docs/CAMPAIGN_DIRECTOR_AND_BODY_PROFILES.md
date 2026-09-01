# AI Campaign Director + Stable Diffusion 체형 프리셋

## 목적

AutoSellerAI의 상품 성장 흐름을 두 단계 더 고도화한다.

1. Stable Diffusion 인물 이미지에 **성인 체형 6종**을 일관된 실사 프롬프트로 적용한다.
2. 상품별 `ProductGrowthWorkflow`를 읽어 **상세페이지 → Threads 카피 → 소셜 비주얼 → Tracking → 예약 게시 → 수익 학습**의 다음 작업을 자동 기획한다.

---

## 1. 성인 체형 프리셋

지원 프로필:

- 매우 슬림
- 슬림
- 슬림 글래머
- 균형형
- 볼륨형
- 운동형

각 프로필은 다음 세부 축으로 변환된다.

- 전체 체형
- 키 인상
- 어깨선
- 흉곽
- 상체 볼륨
- 상체 비율
- 허리·힙 실루엣
- 근육·복부 톤
- 다리 비율 인상

### 숫자 참고치 처리 원칙

사용자가 제공한 키·체중·BMI·체지방률·밑가슴·WHR·브라 사이즈 예시는 데이터에 보존하지만 Stable Diffusion 프롬프트의 정확한 목표값으로 넣지 않는다.

이유:

- txt2img 모델은 실제 cm/kg/BMI를 정확히 계산하지 않는다.
- 수치를 많이 강제하면 몸통·관절·의상 드레이프 왜곡이 늘어날 수 있다.
- 따라서 생성 프롬프트는 `narrow ribcage`, `balanced natural proportions`, `defined core`, `realistic clothing drape` 같은 시각적 자연어를 사용한다.

세부 참고표에는 다음 항목도 보존한다.

- 상체 측면 돌출 인상
- 윗/아랫볼륨 분포
- 자연스러운 형태
- 티셔츠/니트/원피스 착용 시 인상
- 상대적으로 볼륨이 강조되는 의상 요인
- SD 자연어 참고 표현

모든 기본 생성은 **성인·완전 착의 상업/라이프스타일 이미지**를 전제로 한다.

### 기존 생성과 호환

기존 `HumanImageRequest` 또는 생성 이력에 `body_profile`이 없으면 `body_frame`으로 새 6분류를 자동 추론한다.

예:

- `매우 슬림` → 매우 슬림
- `슬림 글래머` → 슬림 글래머
- `균형형` → 균형형
- `볼륨형` → 볼륨형
- `애슬레틱`, `탄탄한 체형`, `러너형`, `근육형` → 운동형

따라서 기존 저장 데이터가 깨지지 않는다.

### UI

Seller OS 사이드바:

`AI 체형 프리셋`

화면에서 프로필을 고르고 `이 프로필 권장값 적용`을 누르면 흉곽/상체/허리/근육/다리 세부값까지 한 번에 맞춘다. 이후 각 항목은 다시 수동 조정할 수 있다.

### REST

`GET /api/v3/image-studio/body-profiles`

반환:

- 6개 프로필
- 생성 프롬프트 조각
- 세부 컨트롤 권장값
- 숫자형 참고 메타데이터
- 확장 참고표
- 흉곽/상체 볼륨/근육/다리 옵션

---

## 2. AI Campaign Director

Campaign Director는 새로운 게시 엔진이 아니다. 기존 `ProductGrowthWorkflow` 위에 올라가는 **기획·오케스트레이션 계층**이다.

입력:

- 상품 사실/원본 이미지
- 상세페이지 준비 상태
- Threads 초안
- 현재 소셜 이미지
- Tracking Link
- 예약/게시 상태
- 주문 귀속
- Content Profit Feedback

출력:

- 추천 Threads 콘텐츠 각도
- 추천 초안 개수
- 필요한 상세페이지 장면 수
- 추천 소셜 비주얼 소스
- 초기 게시 탐색 시간대
- 현재 필요한 작업 목록
- 비용/외부행동 경계
- 품질 게이트와 경고

### 수익 학습

상품별 `ContentStrategyProfile`에 실제 표본이 있으면:

- `preferred_angles`
- `avoid_angles`
- `winning_patterns`
- 주문 수
- 누적 순이익
- 평균 Content Score

를 다음 캠페인 계획에 반영한다.

표본이 충분하지 않으면 현재 설정과 카테고리 기반 휴리스틱을 사용한다.

---

## 3. 실행 Tier

Campaign Director는 작업을 네 종류로 구분한다.

### `local`

비용 없는 로컬/DB 작업.

예:

- 상품 사실 기준 확인
- Tracking Link 준비
- 기존 상품/상세 이미지 재사용

### `ai_compute`

AI 콘텐츠 API를 사용할 수 있는 작업.

예:

- Threads 카피 변형 생성

`allow_ai_content=true`를 명시해야 실행한다.

### `ai_cost`

명시적 유료 이미지 생성 작업.

예:

- reference 기반 상세페이지 AI 이미지 생성

`allow_paid_detail_generation=true`를 명시해야 기존 `image` RQ worker에 등록한다.

### `external_publish`

외부 게시 상태를 미래에 변경하는 작업.

Campaign Director의 `prepare` 단계에서는 실행하지 않는다. 별도 `schedule` API/UI에서 사용자 확인 후 `ScheduledSocialPost`를 생성한다. 실제 게시 책임은 기존 Threads scheduler가 가진다.

---

## 4. REST API

기본 Seller OS API:

`/api/v3`

Campaign Director:

- `GET /product-growth/workflows/{workflow_id}/director`
- `POST /product-growth/workflows/{workflow_id}/director/plan`
- `POST /product-growth/workflows/{workflow_id}/director/prepare`
- `POST /product-growth/workflows/{workflow_id}/director/schedule`

### Plan

부작용 없는 로컬 기획.

```json
{
  "force": false
}
```

### Prepare

```json
{
  "allow_ai_content": true,
  "allow_paid_detail_generation": false,
  "draft_count": 3,
  "force_drafts": false
}
```

기본값은 두 비용 가능 작업 모두 `false`다.

### Schedule

```json
{
  "scheduled_at": "2026-09-01T10:40:00Z",
  "draft_id": 123,
  "media_source": "auto",
  "include_tracking_url": true
}
```

예약 시점에는 카피/이미지를 몰래 새로 생성하지 않는다. 준비된 초안과 자산만 사용한다.

---

## 5. 권장 운영 순서

1. 상품 성장 워크플로우 생성
2. Campaign Director Plan 생성
3. 추천/경고 확인
4. 필요한 경우 Threads AI 카피 허용
5. 필요한 경우 유료 상세 이미지 허용
6. 생성 완료 후 소셜 비주얼 확인
7. 게시 시각과 초안을 명시적으로 선택
8. Threads 예약 게시
9. 클릭/주문 귀속 및 수익 피드백 누적
10. 다음 Campaign Plan에서 실제 성과 기반 각도 재선정

이 구조의 목표는 완전 무감독 게시가 아니라 **비용과 외부행동은 통제하면서 반복적인 캠페인 판단을 자동화**하는 것이다.
