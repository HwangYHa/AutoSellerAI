# AutoSellerAI · Seller OS v3

AutoSellerAI는 공급처 상품 확보부터 판매채널 등록, 고객 주문, 공급처 위탁발주, 배송, 정산, 실제 순이익과 AI 학습까지 이어지는 **위탁판매 운영 OS**입니다.

운영 설계의 핵심은 반복 작업을 자동화하고 사용자는 **승인 · 예외처리 · 전략결정**에만 개입하도록 만드는 것입니다.

## 운영 데이터 척추

```text
Supplier
  ↓
Product ─ ProductVariant
  ↓
SupplierOffer
  ↓
Listing ─ ListingVariant
  ↓
SalesOrder ─ SalesOrderItem
  ↓
Fulfillment
  ↓
SettlementLine
  ↓
LearningSignal
```

외부 상태나 비용을 바꾸는 작업은 별도로 다음 안전 계층을 거칩니다.

```text
User decision
  ↓
ApprovalRequest
  ↓
BackgroundTask (dangerous queue)
  ↓
OperationExecution (unique idempotency key)
  ↓
Marketplace / Supplier API
```

## Seller OS 화면

정상 운영은 `Seller OS` 한 화면을 중심으로 합니다.

- **오늘 할 일**: 승인 대기, 주문 예외, 발주 실패, 자동화 실패
- **상품**: Product/Variant, 공급처 Offer, 판매채널 Listing 통합 관리
- **주문 · 배송**: 주문품목 → 공급처 → Fulfillment → 송장 추적
- **수익**: 주문품목 단위 실제 정산/순이익 원장
- **설정 · 자동화**: 연결, 작업큐, 데이터 건강도, 감사로그

보조 작업공간은 `통합 상품 소싱`, `콘텐츠 스튜디오`, `Threads 마케팅`만 유지합니다. 공급처별/판매채널별 진단 페이지는 전환 기간 동안 코드에는 남을 수 있지만 정상 운영 메뉴에서는 제외합니다.

## 안전 원칙

- 조회·동기화·분석은 안전 작업으로 자동화할 수 있습니다.
- 신규 상품 실제 등록, 공급처 실제 발주, 유료 생성, 대량 변경은 승인 Gate가 필요합니다.
- 동일 외부 작업은 `idempotency_key`로 중복 실행을 차단합니다.
- 위험 작업은 브라우저/Streamlit 프로세스가 직접 실행하지 않고 `dangerous` RQ 큐로 넘깁니다.
- 재고 사입 `PurchaseOrder/MOQ`는 무재고 위탁판매 기본 업무가 아니므로 기본 비활성화합니다.
- 금액 원장은 float가 아닌 정수 KRW 기준의 v3 `SettlementLine`을 사용합니다.

## 런타임 구조

```text
Browser
   │
   ▼
Streamlit Seller OS :8501
   │
   ├── Seller OS Application Layer (app/os)
   │
   ├── Redis/RQ ── sync / automation worker
   │             └ dangerous worker
   │
   └── Database

Seller OS Control Plane API :8001 (localhost binding by default)
Threads API :8000
Redis :6379 (Docker internal)
```

Docker Compose 서비스:

- `autoseller`: Streamlit Seller OS
- `seller-api`: Seller OS FastAPI control plane
- `seller-worker`: `sync`, `automation` 작업
- `seller-dangerous-worker`: 승인된 외부 mutation 전용
- `social-api`: Threads API
- `threads-worker`
- `threads-scheduler`
- `redis`

## 데이터베이스

### 로컬 / 단일 PC

기본값은 기존 운영 DB를 그대로 사용하는 SQLite입니다.

```env
DATABASE_URL=
DB_PATH=data/autoseller.db
```

Seller OS v3는 SQLite에서 foreign key, WAL, busy timeout을 활성화해 로컬 UI/API/worker 동시 접근 안정성을 높입니다.

### 상용 배포

`DATABASE_URL`을 지정하면 공용 SQLAlchemy 런타임을 PostgreSQL로 전환할 수 있습니다.

```env
DATABASE_URL=postgresql+psycopg://user:password@db:5432/autoseller
```

SQLite는 단일 PC 운영용이며 다중 인스턴스 상용 배포는 PostgreSQL을 기준으로 합니다.

## 기존 데이터 이관

기존 운영 DB를 즉시 파괴하지 않습니다. `app/os/bridge.py`의 idempotent bridge가 기존 데이터를 새 `os_*` 데이터 척추로 한 방향 이관합니다.

```text
legacy Product             → os_products
legacy options             → os_product_variants (transition default variant)
SupplierRawProduct         → os_supplier_offers
Listing + MarketplaceIdentity → os_listings / os_listing_variants
PlatformOrder              → os_sales_orders / os_sales_order_items
supplier order/tracking    → os_fulfillments
Order                      → os_settlement_lines
```

새 기능은 `app/os` Application Layer를 기준으로 구현하고, 기존 `app/pipeline.py`와 `gui/legacy_app.py`는 호환/이관 계층으로 축소한 뒤 호출이 0이 되면 제거하는 방향입니다.

## 공급처 및 판매채널

현재 연결 기반:

- 판매채널: Coupang, Naver SmartStore
- 공급처: OwnerClan, Domeggook, Domemai, OnChannel
- AI: Claude, OpenAI

새 공급처는 UI마다 별도 로직을 만들지 않고 `SupplierOrderPort` / 공급처 Connector 규약으로 확장합니다. 특히 실제 자동발주는 공급처별 payload, 주문 시뮬레이션, 취소, 송장 조회가 검증된 드라이버만 활성화합니다.

## 실행

### Docker 권장

```bash
cp .env.example .env
docker compose up --build
```

- Seller OS: `http://localhost:8501`
- Seller OS API health: `http://localhost:8001/health`
- Threads API health: `http://localhost:8000/health`

Seller OS API는 Docker에서 localhost에만 노출합니다. `ENV`가 local/dev/test가 아닌 경우 `SELLER_API_TOKEN`을 반드시 설정해야 `/api/v3/*` Control Plane을 사용할 수 있습니다.

### 로컬 Python

```bash
python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run gui/app.py
```

백그라운드 자동화를 함께 사용하려면 Redis와 RQ worker를 실행해야 합니다.

## 테스트 / CI

```bash
pytest -q
```

GitHub Actions는 다음을 검증합니다.

- 전체 pytest
- 수익 피드백 closed-loop test
- Docker Compose build/start
- Streamlit health
- Seller OS API health
- Threads API health
- Redis
- safe worker
- dangerous worker

## 코드 구조

```text
app/
  os/                   # Seller OS v3 canonical application layer
    models.py            # v3 relational spine
    state.py             # explicit state machines
    approvals.py         # approval + idempotency
    operations.py        # high-risk commands
    dashboard.py         # work queue/read model
    queries.py           # detail/profit read models
    tasks.py             # persistent Redis/RQ tasks
    ports.py             # marketplace/supplier contracts
    bridge.py            # legacy -> v3 migration bridge
    api.py               # FastAPI control plane
    database.py          # SQLite/PostgreSQL runtime bootstrap
  suppliers/             # supplier infrastructure adapters
  platforms/             # marketplace infrastructure clients
  media/                 # product image/detail-page infrastructure
  social/                # Threads

gui/
  app.py                 # default Seller OS entry
  seller_os_v3.py        # unified operating workspace
  pages/                 # auxiliary/migration pages

docs/
  SELLER_OS_V3_ARCHITECTURE.md
```

## 아직 전환 중인 영역

Seller OS v3의 데이터 척추, 승인 Gate, idempotency journal, 작업큐, 통합 UI와 Control Plane은 도입되어 있습니다. 다만 다음 항목은 공급처/판매채널별 검증이 끝날 때까지 레거시 infrastructure를 bridge로 사용합니다.

- 기존 쿠팡/스마트스토어 실제 업로드 구현
- 기존 마켓 주문수집 구현
- 공급처별 실제 주문 payload mapper
- 공급처별 주문취소/송장조회 자동화
- 레거시 수익/정산 데이터의 v3 원장 전환

**실제 공급처 발주는 검증된 v3 주문 드라이버가 준비되기 전에는 승인 상태까지만 진행하고 외부 주문을 자동 실행하지 않습니다.** 안전성보다 자동화 속도를 우선하지 않습니다.

자세한 설계와 제거 기준은 `docs/SELLER_OS_V3_ARCHITECTURE.md`를 참고하세요.
