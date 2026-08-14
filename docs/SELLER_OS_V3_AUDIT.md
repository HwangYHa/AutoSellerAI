# Seller OS v3 전면 감사 결과

기준일: 2026-08-14

이 문서는 기존 코드를 설명하기 위한 문서가 아니라 **향후 AutoSellerAI가 다시 복잡해지는 것을 막는 제거/통합 기준**이다.

## 1. 최종 제품 경계

AutoSellerAI의 정상 운영 경로는 하나다.

```text
Supplier
  ↓
Product / Variant
  ↓
SupplierOffer / OfferVerification
  ↓
Listing / ListingVariant
  ↓
SalesOrder / SalesOrderItem
  ↓
Fulfillment
  ↓
SettlementLine
  ↓
LearningSignal
```

사람이 담당하는 일:

1. 승인
2. 예외처리
3. 전략결정

나머지는 connector/application service/background worker가 담당한다.

---

## 2. UI/UX 감사

### 문제

- 공급처별, 판매채널별, 이미지, SEO, 재고, 주문, 수익 화면이 각각 독립 업무처럼 존재했다.
- 같은 상품을 여러 메뉴에서 다시 찾고 수정해야 했다.
- 시스템 개발 단계/기술 용어가 운영 메뉴에 그대로 노출됐다.
- `Inventory/MOQ/PurchaseOrder`와 고객 주문의 위탁발주가 사용자 관점에서 혼동될 수 있었다.

### 결정

정상 운영 UI를 5개 업무면으로 제한한다.

- 오늘 할 일
- 상품
- 주문 · 배송
- 수익
- 설정 · 자동화

보조 작업공간은 상품 소싱, 콘텐츠 제작, 마케팅뿐이다. 보조 화면은 독립 상태를 소유하지 않고 canonical Product를 수정한다.

공급처/판매채널별 진단 페이지는 마이그레이션 기간 동안만 코드에 남길 수 있으며 정상 사이드바에는 노출하지 않는다.

---

## 3. 데이터 감사

### 문제

- legacy `Product`, `Listing`, `PlatformOrder`, `Order`, `SupplierRawProduct` 간 관계 상당수가 정수 ID 관례에 의존했다.
- 쿠팡 sellerProductId/vendorItemId처럼 외부 ID 종류가 달라 주문 연결이 깨질 수 있었다.
- 옵션이 JSON 중심이라 신발 사이즈/색상 같은 실제 주문 단위를 안정적으로 추적하기 어려웠다.
- 공급처 재고와 내 재고 개념이 섞였다.
- legacy supplier normalized data가 모르는 값을 0/3000/중국 같은 기본값으로 채우는 구간이 있었다.

### 결정

- 신규 데이터는 `os_*` ForeignKey canonical schema만 사용한다.
- Product와 ProductVariant를 분리한다.
- 공급처 조건은 SupplierOffer로 분리한다.
- 위탁판매 재고의 기준은 `SupplierOffer.stock_qty`다.
- `Inventory/PurchaseOrder`는 stocked-product 기능으로 격리한다.
- 신규 supplier contract는 모르는 값을 `None`으로 전달한다.
- `OfferVerification`이 공급가/배송비/재고/MOQ/옵션 식별정보의 known/unknown을 별도로 보관한다.
- legacy MarketplaceIdentity는 bridge가 v3 ListingVariant로 흡수한다.

---

## 4. 주문/발주 감사

### 문제

- 고객 주문과 재고 사입 발주가 서로 다른 목적이지만 UI/코드에서 가까이 존재했다.
- 공급처 상품 단위 매칭만으로는 옵션이 다른 상품을 잘못 발주할 수 있다.
- 외부 API 호출을 두 번 실행했을 때 중복 상품등록/중복 발주 위험이 있다.
- 공급가나 배송비가 승인 후 바뀌어도 실행 시 재검증하지 않으면 승인 내용과 실제 비용이 달라진다.

### 결정

실제 발주는 아래 조건을 전부 만족해야 한다.

```text
SalesOrderItem.product_id 연결
AND ProductVariant 연결
AND 정확한 SupplierOffer 선택
AND OfferVerification 통과
AND 공급가/배송비/재고/MOQ 재검증
AND ApprovalRequest approved
AND verified SupplierOrderPort
AND unique idempotency_key
AND dangerous worker
```

승인 시점과 실행 시점에 조건을 각각 검사한다.

공급처 로그인 가능 여부와 실제 자동발주 가능 여부는 완전히 분리한다. 주문 payload mapping, simulation, cancellation, tracking이 검증된 driver만 verified로 등록할 수 있다.

---

## 5. 상태관리 감사

### 문제

- 여러 모듈이 문자열 상태를 직접 생성/수정했다.
- 화면마다 완료의 의미가 달랐다.

### 결정

상태 전이는 `app/os/state.py`에 한정한다.

불법 shortcut은 거부한다. 예외는 정상 상태를 조작해 숨기지 않고 `exception_code`와 Work Queue로 올린다.

---

## 6. Background Job 감사

### 문제

- Streamlit 프로세스 내부 daemon thread는 브라우저/프로세스 생명주기와 업무 생명주기가 결합된다.
- 스케줄러/RQ/페이지별 작업 실행이 중복되어 실행 주체가 불분명했다.

### 결정

```text
UI / API / Safe Scheduler
        ↓
OSBackgroundTask journal
        ↓
Redis / RQ
        ↓
worker
        ↓
DB result
```

Queue를 분리한다.

- `sync`: 카탈로그/주문/관계 동기화
- `automation`: AI/콘텐츠 등 안전 자동화
- `dangerous`: 실제 외부 mutation

`dangerous`는 전용 worker만 소비한다. Scheduler는 dangerous 작업을 만들 수 없다.

---

## 7. API 감사

### 문제

- UI가 ORM과 외부 client를 직접 호출하면 프론트엔드 교체/테스트/보안경계를 만들기 어렵다.

### 결정

`app/os`가 Application Layer다. `app/os/api.py`는 Control Plane이다.

- UI는 read model/application service만 호출한다.
- HTTP request 생명주기에서 실제 외부 mutation을 수행하지 않는다.
- production API는 Seller API bearer token을 요구한다.
- Docker 기본 노출은 localhost다.

향후 React/Next.js로 UI를 교체해도 Application/API 계약은 유지한다.

---

## 8. DB/마이그레이션 감사

### 문제

- `create_all()`만으로 상용 DB schema version을 관리할 수 없다.
- SQLite는 다중 worker/다중 instance 확장에 한계가 있다.

### 결정

- 기존 단일 PC 운영 DB: SQLite 유지, WAL/foreign_keys/busy_timeout 적용
- 신규 상용 DB: PostgreSQL
- canonical `os_*`: Alembic migration 관리
- legacy table은 v3 Alembic 소유 범위 밖에 둔다.
- 기존 DB는 파괴 migration 대신 idempotent Strangler bridge로 이관한다.

---

## 9. AI 감사

### 문제

생성형 AI 기능을 많이 붙이는 것 자체가 판매 자동화의 핵심은 아니다.

### 결정

AI의 핵심 입력은 실제 결과다.

```text
실제 정산 수익
반품비
플랫폼 수수료
공급처 실패/품절
배송 지연
광고 성과
→ LearningSignal
→ 다음 상품/가격/콘텐츠 판단
```

`SettlementLine`은 실제 손익 Source of Truth이며 `LearningSignal`은 이 결과를 모델이 소비할 수 있는 관측값으로 변환한다.

---

## 10. 삭제/격리 결정

| 대상 | 결정 | 이유 |
|---|---|---|
| `gui/legacy_app.py` | 정상 운영 경로 제거, 최종 삭제 대상 | 대형 monolith / 중복 UI |
| `app/pipeline.py` | 신규 기능 금지, adapter/bridge로만 사용 후 삭제 | God module |
| legacy daemon background jobs | 신규 사용 금지 | 비지속성 / 브라우저 생명주기 결합 |
| `Inventory/MOQ/PurchaseOrder` | dropship UI에서 격리 | 고객 위탁발주와 다른 업무 |
| 공급처별 일상 메뉴 | 통합 설정으로 이동 | 메뉴 파편화 |
| 판매채널별 일상 메뉴 | 통합 Seller OS로 이동 | 동일 상품/주문 반복 처리 |
| legacy logical ID joins | bridge 기간만 허용 | FK/variant canonical spine로 교체 |
| 임의 supplier 기본값 | v3 신규 connector에서 금지 | 비용/재고 오판 위험 |

---

## 11. 현재 의도적으로 남긴 전환 계층

아래는 보존이 목표가 아니라 **데이터 손실 없이 제거하기 위한 임시 경계**다.

- 기존 쿠팡/스마트스토어 업로드 구현
- 기존 마켓 주문수집 구현
- 기존 Supplier adapters
- legacy Product/Listing/PlatformOrder/Order
- `app/pipeline.py`의 일부 외부 client orchestration

신규 코드가 이 계층을 직접 호출하면 안 된다. v3 worker/port/bridge 내부에서만 허용한다.

---

## 12. Commercial-ready 판정 기준

다음을 모두 만족하기 전에는 특정 외부 connector를 “자동발주 완료”라고 표현하지 않는다.

- 실제 공급처 ProductVariant ID 검증
- 공급가/배송비/재고/MOQ 검증
- 온라인 재판매 조건 검증이 필요한 상품의 근거 보관
- 정품 증빙이 필요한 상품의 근거 보관
- 주문 simulation 성공
- 실제 소액 test order 성공
- 주문 취소 test 성공
- tracking 조회 성공
- 동일 승인 2회 실행 idempotency test 성공
- 공급가 변경/재고 부족 race-condition 차단 test 성공

이 기준을 통과한 공급처 driver만 `verified=True`로 등록한다.
