# AutoSellerAI - 1단계 상품 발굴 자동화 엔진

실무형 구조를 기준으로 FastAPI + PostgreSQL + Redis 기반의 상품 발굴 엔진을 구현했다.

## 구현 범위 (1단계)

- 쿠팡 인기상품 크롤링 (현재는 교체 가능한 Mock Client로 구현)
- 스마트스토어 인기상품 분석 (현재는 교체 가능한 Mock Client로 구현)
- 리뷰 증가율 계산
- 검색량 분석
- 예상 순이익 계산
- 경쟁 강도 점수화
- 자동 추천 점수 산정

## 구현 범위 (2단계 시작 - 도매가 분석)

- 도매 단가/최소주문수량(MOQ)/리드타임/불량률 기반 분석
- 실판매가 대비 총원가 및 매출총이익률 계산
- 리스크 점수 및 도매 경쟁력 점수 계산
- 공급처 다중 비교 API 제공 (GUI 테이블/랭킹 표시 용도)
- 추천 등급(A/B/C/D) 제공

## 아키텍처

```text
app/
  api/                 # FastAPI Router
  core/                # 설정, 로깅, 예외
  db/                  # SQLAlchemy 세션, 베이스
  models/              # ORM 모델
  repositories/        # Repository Pattern
  schemas/             # Request/Response 스키마
  services/            # 도메인 로직
  utils/               # 공통 함수
tests/                 # 단위/통합 테스트
```

## 실행 방법

1) 환경 변수 파일 준비

```bash
cp .env.example .env
```

2) Docker 실행

```bash
docker compose up --build
```

3) API 확인

- Health: `GET http://localhost:8000/health`
- 분석: `POST http://localhost:8000/api/v1/discovery/analyze`
- 추천 목록: `GET http://localhost:8000/api/v1/discovery/recommendations?limit=20`
- 도매 분석: `POST http://localhost:8000/api/v1/wholesale/analyze`
- 도매 비교: `POST http://localhost:8000/api/v1/wholesale/compare`
- 도매 상위: `GET http://localhost:8000/api/v1/wholesale/top?limit=20`

## 테스트 실행

```bash
pytest -q
```

## API 예시

### 상품 분석

`POST /api/v1/discovery/analyze`

```json
{
  "keyword": "무선 청소기",
  "category": "가전",
  "sourcing_cost": 50000,
  "sale_price": 109000,
  "shipping_cost": 3000,
  "marketing_cost_ratio": 0.05,
  "fee_ratio": 0.12
}
```

## 개발 순서 추천 (요청하신 순서 반영)

1. 상품 발굴 엔진 (완료)
2. 도매가 분석 엔진 (진행 시작)
3. 상세페이지 생성 엔진
4. 업로드 자동화 엔진
5. 주문 자동화 엔진
6. 관리자 시스템

## 2단계 이후 확장 포인트

- Marketplace Client를 실제 API/크롤러 어댑터로 교체
- Celery/RQ 기반 비동기 수집 파이프라인 추가
- Alembic 마이그레이션 도입
- 추천 모델 고도화(가중치 학습, A/B 테스트)
- 관리자 대시보드 및 권한 모델 도입
