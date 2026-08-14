# AutoSellerAI Seller OS v3 — 전면 감사·재설계 기준

## 1. 제품 정의

AutoSellerAI는 단순 상품등록 툴이 아니다. 운영 기준 제품은 다음 데이터 척추를 관리하는 **위탁판매 운영 OS**다.

`Supplier → Product/Variant → SupplierOffer → Listing/Variant → SalesOrder/Item → Fulfillment → SettlementLine → LearningSignal`

사용자는 반복 작업을 직접 수행하지 않는다. 사용자에게 노출할 업무는 **승인, 예외처리, 전략결정** 세 가지뿐이다.

---

## 2. 기존 구조 감사 결과

### 제거/격리 대상

- `app/pipeline.py`: 지나치게 많은 업무가 한 모듈에 집중된 God module. 신규 기능 추가 금지, 호환 계층으로만 사용한다.
- `gui/legacy_app.py`: 정상 운영 경로에서 완전 제외한다.
- `app/services/background_jobs.py`: 프로세스 로컬 daemon thread. 브라우저/프로세스 장애에 대한 지속성이 없으므로 신규 사용 금지한다.
- UI에서 직접 ORM/외부 API를 호출하는 흐름: v3 Control Plane으로 이동한다.
- `Inventory/PurchaseOrder/MOQ` 재고 사입 흐름: 위탁판매 기본 OS에서 숨기고 별도 stocked-product 기능으로 격리한다.
- SupplierRawProduct/SupplierWorkflowItem/Product/Listing/PlatformOrder/Order 사이의 비공식 논리 연결: v3 FK 데이터 척추로 교체한다.
- 공급처별 연결 화면을 일상 메뉴로 노출하는 구조: 연결 설정으로 통합한다.

### 유지하되 Infrastructure로 강등

- 쿠팡/스마트스토어 API client
- 오너클랜/도매꾹/도매매/온채널 connector
- 이미지 추출/복구
- SEO/AI 엔진
- 수익 계산 엔진
- Circuit breaker / rate limiter

이들은 UI나 비즈니스 상태를 소유하지 않고 v3 Application Service의 Port/Adapter로만 사용한다.

---

## 3. 최종 메뉴 구조

### Seller OS

1. **오늘 할 일**
   - 승인 대기
   - 주문 예외
   - 공급처 발주 실패
   - 자동화 실패
   - 품절/가격 급변 등 중요 알림

2. **상품**
   - 판매 후보 / 검토 / 준비완료 / 판매중 / 중지
   - Product + Variant 단일 상세 화면
   - 공급처 Offer, 판매채널 Listing을 같은 화면에서 확인
   - 이미지/SEO/가격은 Product Detail의 서브 영역으로 흡수

3. **주문 · 배송**
   - SalesOrder → SalesOrderItem → Fulfillment → Tracking 한 화면
   - 공급처 발주는 주문 품목 단위
   - 사입 PurchaseOrder는 여기에서 절대 노출하지 않음

4. **수익**
   - 예상수익과 실제수익 구분
   - 주문품목 단위 수익 원장
   - 플랫폼/상품/공급처별 손익
   - 정산 확정값을 AI 학습의 기준값으로 사용

5. **설정 · 자동화**
   - 판매채널/공급처/AI 연결
   - 스케줄/작업 큐
   - 데이터 건강도
   - 감사 로그
   - 안전정책

### 보조 작업공간

- 통합 상품 소싱
- 콘텐츠 스튜디오(이미지/상세/SEO)
- 마케팅(Threads)

보조 작업공간은 Seller OS의 데이터 척추를 사용하며 독립적인 상태를 만들지 않는다.

---

## 4. 데이터 원칙

### Product

플랫폼이나 공급처에 종속되지 않는 내부 상품 Master다.

### ProductVariant

색상/사이즈/용량 등 실제 주문 가능 단위를 나타낸다. 신발의 260/265/270은 반드시 별도 Variant다.

### SupplierOffer

공급처의 특정 Product/Variant 판매조건 스냅샷이다.

- 공급가
- 배송비
- 재고
- MOQ
- 출고 리드타임
- 공급처 상품/옵션 ID

`Inventory`와 다르다. 위탁판매의 핵심 재고는 **내 재고가 아니라 SupplierOffer.stock_qty**다.

### Listing / ListingVariant

쿠팡/스마트스토어 판매상품과 옵션 ID를 내부 Product/Variant에 연결한다.

### SalesOrder / SalesOrderItem

판매채널 주문을 주문/품목으로 정규화한다. 한 주문에 여러 품목이 있어도 각 품목별 공급처/수익/배송을 독립적으로 추적한다.

### Fulfillment

공급처 실제 발주를 나타낸다. SalesOrderItem 하나당 기본 하나의 Fulfillment를 가진다.

### SettlementLine

주문품목 단위 회계 원장이다. 금액은 float가 아니라 **정수 KRW**로 저장한다.

### LearningSignal

정산 확정 수익, 반품, 품절, 배송지연, 광고성과 등 AI가 다음 상품 선택에 이용할 관측값이다.

---

## 5. 상태관리

상태 문자열을 UI/connector가 임의 생성하지 않는다.

- Product: `draft → review → ready → active → paused/archived`
- Listing: `draft → pending_approval → publishing → active/failed`
- Order: `new → ready_to_fulfill → fulfilling → shipped → completed`
- OrderItem: `new → ready → approved → ordered → shipped → completed`
- Fulfillment: `pending_approval → approved → ordering → ordered → shipped → completed`
- Approval: `pending → approved/rejected → consumed`

예외는 상태를 우회하지 않고 `exception_code`와 Work Queue에 나타난다.

---

## 6. 승인 Gate / 중복 실행 방지

외부 상태나 비용을 바꾸는 작업은 반드시 두 개의 레코드를 남긴다.

### ApprovalRequest

사용자가 **무엇을 승인했는지** 정확한 payload hash와 함께 보관한다.

### OperationExecution

실제 외부 API 호출을 나타내며 `idempotency_key`가 unique다.

따라서 같은 승인/동일 payload를 두 번 클릭해도 외부 API를 두 번 호출하지 않는다.

승인 필수 작업:

- 신규 상품 등록
- 판매상품 수정/중지/삭제
- 공급처 실제 발주
- 공급처 주문 취소
- 유료 AI 생성
- 대량 가격 변경

조회/동기화/분석은 승인 없이 자동 실행할 수 있다.

---

## 7. 백그라운드 작업

### 폐기

Streamlit daemon thread가 업무를 소유하는 구조.

### 표준

`UI/API → OSBackgroundTask(DB) → Redis/RQ → Worker → 결과 DB`

브라우저를 닫아도 작업은 계속된다. UI는 task id만 조회한다.

Queue 분리:

- `sync`: 카탈로그/주문/재고/가격 동기화
- `automation`: 이미지/SEO/AI 분석 등 안전 자동화
- `dangerous`: 승인 완료 후 실제 외부 mutation

`dangerous` queue는 승인 검증과 idempotency 검증을 다시 수행한다.

---

## 8. 프레임워크/배포 원칙

### 현재 전환기

- Streamlit: 운영 UI
- FastAPI: Seller OS Control Plane API
- SQLAlchemy 2
- SQLite: 로컬 개발/단일 PC
- Redis + RQ: 지속성 있는 작업 큐

### 상용 배포

- Frontend: React/Next.js 또는 동일 수준 SPA
- API: FastAPI
- DB: PostgreSQL
- Queue: Redis + RQ
- Object Storage/CDN: 이미지/생성 콘텐츠
- Reverse Proxy/TLS

핵심 원칙은 프론트엔드 교체와 무관하게 `app/os` Application/API 계약을 유지하는 것이다. Streamlit은 최종 비즈니스 로직을 소유하지 않는다.

---

## 9. Migration Strategy

현재 운영 DB를 파괴적으로 변환하지 않는다.

1. `os_*` canonical tables 생성
2. `migrate_legacy_to_os()`로 기존 Product/Listing/PlatformOrder/Order를 idempotent하게 이관
3. Seller OS 화면을 v3 read model로 전환
4. 신규 mutation을 v3 service로 이동
5. supplier/marketplace connector를 하나씩 v3 port에 직접 연결
6. legacy write가 0이 되면 `pipeline.py`, legacy workflow/table 제거

이 방식은 레거시 보존이 목적이 아니라 **운영 중 데이터 손실 없이 제거하기 위한 Strangler migration**이다.

---

## 10. 완료 판정 기준

다음 조건을 만족해야 v3 전환 완료로 본다.

- 일상 업무는 Seller OS 한 화면에서 가능
- 실제 외부 mutation에 direct API call 경로가 없음
- 모든 주문 품목이 ProductVariant와 SupplierOffer에 연결되거나 명시적 exception 상태
- 모든 실제 발주에 Approval + OperationExecution 존재
- 모든 외부 mutation은 idempotent
- 브라우저 종료가 작업 실행에 영향 없음
- 정산은 주문품목 단위 integer KRW 원장
- Inventory/PurchaseOrder는 dropship 업무에서 분리
- legacy_app 정상 경로 0건
- pipeline.py 신규 호출 0건 이후 삭제
