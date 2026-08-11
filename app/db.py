"""SQLite DB — products, listings, market_insights, orders, settlement_periods, tax_summaries,
inventory, purchase_orders, purchase_order_items, stock_movements, seo_revisions."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from sqlalchemy import create_engine, DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(30))           # domeggook | onchannel
    source_id: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(Text, default="")

    name: Mapped[str] = mapped_column(String(300))
    supply_price: Mapped[float] = mapped_column(Float)
    sell_price: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(200), default="")
    brand: Mapped[str] = mapped_column(String(120), default="")
    origin: Mapped[str] = mapped_column(String(100), default="중국")
    material: Mapped[str] = mapped_column(String(200), default="")

    images: Mapped[str] = mapped_column(Text, default="[]")         # JSON list
    detail_images: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    options: Mapped[str] = mapped_column(Text, default="[]")        # JSON list
    detail_html: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    # draft → ready → listed

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(30))               # coupang | smartstore
    platform_id: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    # pending | success | failed
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketInsight(Base):
    __tablename__ = "market_insights"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(200), index=True)

    trend_data: Mapped[str] = mapped_column(Text, default="[]")      # JSON [{period, ratio}]
    shopping_stats: Mapped[str] = mapped_column(Text, default="{}")  # JSON ShoppingStats
    coupang_best: Mapped[str] = mapped_column(Text, default="[]")    # JSON [CoupangBestItem]

    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[str] = mapped_column(Text, default="{}")  # JSON {trend,competition,margin,demand}
    recommendation: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")             # JSON list[str]
    risk_factors: Mapped[str] = mapped_column(Text, default="[]")     # JSON list[str]

    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)     # coupang | smartstore
    platform_order_id: Mapped[str] = mapped_column(String(200), default="")

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_sale_price: Mapped[float] = mapped_column(Float)             # 실제 판매가(VAT포함)
    unit_supply_price: Mapped[float] = mapped_column(Float)           # 공급가
    shipping_fee_paid: Mapped[float] = mapped_column(Float, default=3000)   # 판매자 배송비 지출
    shipping_fee_charged: Mapped[float] = mapped_column(Float, default=0)   # 구매자 청구 배송비

    platform_fee_rate: Mapped[float] = mapped_column(Float, default=0.108)
    platform_fee: Mapped[float] = mapped_column(Float, default=0)
    ad_cost: Mapped[float] = mapped_column(Float, default=0)
    return_cost: Mapped[float] = mapped_column(Float, default=0)

    gross_revenue: Mapped[float] = mapped_column(Float, default=0)
    supply_cost: Mapped[float] = mapped_column(Float, default=0)
    net_shipping_cost: Mapped[float] = mapped_column(Float, default=0)
    gross_profit: Mapped[float] = mapped_column(Float, default=0)
    vat_payable: Mapped[float] = mapped_column(Float, default=0)
    net_profit: Mapped[float] = mapped_column(Float, default=0)
    margin_rate: Mapped[float] = mapped_column(Float, default=0)

    status: Mapped[str] = mapped_column(String(30), default="completed", index=True)
    # ordered | shipped | completed | returned | cancelled

    ordered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    memo: Mapped[str] = mapped_column(Text, default="")


class SettlementPeriod(Base):
    __tablename__ = "settlement_periods"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    period_label: Mapped[str] = mapped_column(String(50), index=True)   # e.g. "2026-06-1st"
    period_start: Mapped[datetime] = mapped_column(DateTime)
    period_end: Mapped[datetime] = mapped_column(DateTime)

    order_count: Mapped[int] = mapped_column(Integer, default=0)
    gross_revenue: Mapped[float] = mapped_column(Float, default=0)
    supply_cost: Mapped[float] = mapped_column(Float, default=0)
    platform_fee: Mapped[float] = mapped_column(Float, default=0)
    shipping_cost: Mapped[float] = mapped_column(Float, default=0)
    ad_cost: Mapped[float] = mapped_column(Float, default=0)
    return_cost: Mapped[float] = mapped_column(Float, default=0)
    vat_payable: Mapped[float] = mapped_column(Float, default=0)
    net_profit: Mapped[float] = mapped_column(Float, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaxSummary(Base):
    __tablename__ = "tax_summaries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    quarter: Mapped[int] = mapped_column(Integer, default=0)   # 0=연간, 1~4=분기

    gross_revenue: Mapped[float] = mapped_column(Float, default=0)
    supply_cost: Mapped[float] = mapped_column(Float, default=0)
    platform_fee: Mapped[float] = mapped_column(Float, default=0)
    other_deductibles: Mapped[float] = mapped_column(Float, default=0)
    taxable_income: Mapped[float] = mapped_column(Float, default=0)

    vat_payable: Mapped[float] = mapped_column(Float, default=0)
    income_tax: Mapped[float] = mapped_column(Float, default=0)
    local_tax: Mapped[float] = mapped_column(Float, default=0)
    total_tax: Mapped[float] = mapped_column(Float, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)

    qty_on_hand: Mapped[int] = mapped_column(Integer, default=0)        # 현재 보유 재고
    qty_reserved: Mapped[int] = mapped_column(Integer, default=0)       # 주문 예약 재고
    qty_incoming: Mapped[int] = mapped_column(Integer, default=0)       # 입고 예정 (발주 중)

    safety_stock: Mapped[int] = mapped_column(Integer, default=10)      # 안전 재고
    reorder_point: Mapped[int] = mapped_column(Integer, default=20)     # 재발주 트리거 포인트
    moq: Mapped[int] = mapped_column(Integer, default=1)                # 최소 발주 수량
    reorder_qty: Mapped[int] = mapped_column(Integer, default=50)       # 표준 발주 수량
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)     # 납기일 (일)

    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)        # 단위 공급가 스냅샷
    location: Mapped[str] = mapped_column(String(100), default="")      # 창고 위치

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    po_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    supplier: Mapped[str] = mapped_column(String(100), default="")      # 공급처명

    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    # draft | confirmed | ordered | received | cancelled

    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    memo: Mapped[str] = mapped_column(Text, default="")

    ordered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)

    qty_received: Mapped[int] = mapped_column(Integer, default=0)       # 실제 입고 수량


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)

    movement_type: Mapped[str] = mapped_column(String(30), index=True)
    # in_purchase | in_adjust | out_sale | out_adjust | out_return

    quantity: Mapped[int] = mapped_column(Integer)                      # +증가 / -감소
    qty_after: Mapped[int] = mapped_column(Integer, default=0)          # 변동 후 재고
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # order_id or po_id
    reference_type: Mapped[str] = mapped_column(String(30), default="")        # order | po | manual
    memo: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CircuitBreakerState(Base):
    __tablename__ = "circuit_breaker_states"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(20), default="closed")  # closed|open|half_open
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class HealthCheckLog(Base):
    __tablename__ = "health_check_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)   # ok|degraded|down|unknown
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(String(200), default="")
    error: Mapped[str] = mapped_column(String(300), default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    level: Mapped[str] = mapped_column(String(20), index=True)    # critical | warning | info | success
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="ok") # ok | failed
    error: Mapped[str] = mapped_column(String(300), default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300), default="")
    cron_expr: Mapped[str] = mapped_column(String(60))          # "0 3 * * *"
    enabled: Mapped[bool] = mapped_column(default=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), default="")  # ok | failed | running
    last_error: Mapped[str] = mapped_column(String(500), default="")
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class JobRunLog(Base):
    __tablename__ = "job_run_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(60), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | failed
    result: Mapped[str] = mapped_column(Text, default="")     # JSON 요약
    error: Mapped[str] = mapped_column(String(500), default="")


class SupplierWorkflowItem(Base):
    """공급사별 상태 머신(State Machine) 워크플로우 추적.

    공급사마다 상품 → 등록까지의 프로세스가 다르므로 상태를 별도 테이블로 관리.

    도매꾹/도매매 상태 흐름:
      DISCOVERED → AI_SCORED → CONTENT_GENERATED → LISTED | REJECTED

    온채널 상태 흐름 (승인 프로세스 포함):
      DISCOVERED → AI_SCORED → APPROVAL_PENDING → APPROVAL_REQUESTED
                                                 → APPROVED → CONTENT_GENERATED → LISTED
                                                 → REJECTED (재신청 가능)
    """
    __tablename__ = "supplier_workflow_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    supplier_id: Mapped[str] = mapped_column(String(30), index=True)
    raw_product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # FK to supplier_raw_products
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)      # FK to products (listed 이후)

    # ── 상태 머신 ────────────────────────────────────────────────────────────
    workflow_state: Mapped[str] = mapped_column(String(50), default="DISCOVERED", index=True)
    # DISCOVERED | AI_SCORED | APPROVAL_PENDING | APPROVAL_REQUESTED
    # | APPROVED | CONTENT_GENERATED | LISTED | REJECTED | SKIPPED

    state_changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    state_history: Mapped[str] = mapped_column(Text, default="[]")  # JSON [{state, ts}]
    error_message: Mapped[str] = mapped_column(String(500), default="")

    # ── 상품 식별 ─────────────────────────────────────────────────────────────
    raw_id: Mapped[str] = mapped_column(String(200), index=True)    # 공급사 원본 상품 ID
    product_name: Mapped[str] = mapped_column(String(400), default="")
    supply_price: Mapped[float] = mapped_column(Float, default=0.0)

    # ── AI 점수 ──────────────────────────────────────────────────────────────
    ai_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[str] = mapped_column(Text, default="{}")  # JSON

    # ── 온채널 전용: 승인 프로세스 ───────────────────────────────────────────
    approval_status: Mapped[str] = mapped_column(String(30), default="")
    # "" | PENDING | REQUESTED | APPROVED | REJECTED
    approval_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approval_result_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approval_reject_reason: Mapped[str] = mapped_column(String(300), default="")
    approval_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    approval_max_retries: Mapped[int] = mapped_column(Integer, default=2)

    # ── 콘텐츠 생성 ──────────────────────────────────────────────────────────
    content_generated: Mapped[bool] = mapped_column(default=False)
    keywords_generated: Mapped[bool] = mapped_column(default=False)
    faq_generated: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_workflow_supplier_raw", "supplier_id", "raw_id"),
        Index("ix_workflow_state", "workflow_state", "supplier_id"),
    )


class SupplierRawProduct(Base):
    """공급사 원본 데이터 저장소 — 정규화 전 raw JSON 보존.

    product_master(products 테이블)와 별도로 원본을 보관해
    재정규화·디버깅·감사 이력으로 활용한다.
    """
    __tablename__ = "supplier_raw_products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[str] = mapped_column(String(30), index=True)  # domeggook|domemai|onchannel
    raw_id: Mapped[str] = mapped_column(String(200), index=True)      # 공급사 원본 상품 ID
    raw_url: Mapped[str] = mapped_column(Text, default="")

    # 원본 데이터 그대로
    raw_name: Mapped[str] = mapped_column(String(400), default="")
    raw_price: Mapped[float] = mapped_column(Float, default=0.0)
    raw_moq_field: Mapped[str] = mapped_column(String(50), default="moq")  # 원본 필드명 기록
    raw_moq_value: Mapped[int] = mapped_column(Integer, default=1)
    raw_stock: Mapped[int] = mapped_column(Integer, default=0)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")             # 전체 원본 JSON

    # 정규화 후 product_id (연결된 경우)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # 정규화 결과
    normalized_score: Mapped[float] = mapped_column(Float, default=0.0)  # AI 점수 (0-100)
    is_selected: Mapped[bool] = mapped_column(default=False)             # 등록 대상 선별 여부
    reject_reason: Mapped[str] = mapped_column(String(200), default="")  # 탈락 사유

    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_supplier_raw_supplier_raw", "supplier_id", "raw_id"),
    )


class PlatformOrder(Base):
    """플랫폼(쿠팡·스마트스토어)에서 수집한 운영 주문 — 발주·송장 자동화용."""
    __tablename__ = "platform_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    platform: Mapped[str] = mapped_column(String(30), index=True)           # coupang | smartstore
    platform_order_id: Mapped[str] = mapped_column(String(200), index=True) # 쿠팡 orderId / SS orderId
    platform_item_id: Mapped[str] = mapped_column(String(200), default="")  # orderItemId / productOrderId
    vendor_item_id: Mapped[str] = mapped_column(String(200), default="")    # 쿠팡 vendorItemId (재고 업데이트용)
    origin_product_no: Mapped[str] = mapped_column(String(200), default="") # 스마트스토어 originProductNo

    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # 내부 product_id
    product_name: Mapped[str] = mapped_column(String(300), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)

    buyer_name: Mapped[str] = mapped_column(String(100), default="")
    receiver_name: Mapped[str] = mapped_column(String(100), default="")
    receiver_phone: Mapped[str] = mapped_column(String(50), default="")
    shipping_address: Mapped[str] = mapped_column(Text, default="")
    shipping_message: Mapped[str] = mapped_column(String(300), default="")

    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    # new | fulfilling | shipped | completed | cancelled

    supplier: Mapped[str] = mapped_column(String(50), default="")           # 발주 공급처
    supplier_order_id: Mapped[str] = mapped_column(String(200), default="") # 공급처 주문번호
    delivery_company: Mapped[str] = mapped_column(String(50), default="")   # 배송사 코드
    tracking_number: Mapped[str] = mapped_column(String(100), default="")   # 운송장 번호
    invoice_registered: Mapped[bool] = mapped_column(default=False)         # 플랫폼 송장 등록 완료

    ordered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_platform_orders_platform_order", "platform", "platform_order_id"),
    )


class ProductPerformance(Base):
    """플랫폼 상품 성과 일별 스냅샷 — 노출·클릭·구매 추적."""
    __tablename__ = "product_performance"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    listing_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)           # coupang | smartstore
    platform_product_id: Mapped[str] = mapped_column(String(200), default="")

    snapshot_date: Mapped[str] = mapped_column(String(10), index=True)      # "YYYY-MM-DD"
    days_since_listed: Mapped[int] = mapped_column(Integer, default=0)

    # 당일 지표
    impressions: Mapped[int] = mapped_column(Integer, default=0)            # 노출수
    clicks: Mapped[int] = mapped_column(Integer, default=0)                 # 클릭수
    orders: Mapped[int] = mapped_column(Integer, default=0)                 # 주문수
    revenue: Mapped[float] = mapped_column(Float, default=0.0)              # 매출 (원)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)                  # clicks/impressions
    cvr: Mapped[float] = mapped_column(Float, default=0.0)                  # orders/clicks

    # 누적 지표 (등록일 이후 전체)
    cum_impressions: Mapped[int] = mapped_column(Integer, default=0)
    cum_clicks: Mapped[int] = mapped_column(Integer, default=0)
    cum_orders: Mapped[int] = mapped_column(Integer, default=0)
    cum_revenue: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_perf_product_date", "product_id", "platform", "snapshot_date"),
    )


class ProductSurvivalStatus(Base):
    """상품 생존율 분석 결과 — 7/14/30일 윈도우별 판정."""
    __tablename__ = "product_survival_status"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    analysis_date: Mapped[str] = mapped_column(String(10), index=True)  # "YYYY-MM-DD"
    window_days: Mapped[int] = mapped_column(Integer, default=7)         # 7 | 14 | 30

    days_since_listed: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)
    cvr: Mapped[float] = mapped_column(Float, default=0.0)

    survival_score: Mapped[float] = mapped_column(Float, default=0.0)    # 0~100
    # HEALTHY: 생존 / WATCH: 관찰 / DELETE_CANDIDATE: 삭제후보 / DELETED: 삭제완료
    status: Mapped[str] = mapped_column(String(30), default="WATCH", index=True)
    reason: Mapped[str] = mapped_column(String(300), default="")
    auto_action: Mapped[str] = mapped_column(String(50), default="")     # "" | delisted | price_adjusted

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_survival_product_window", "product_id", "platform", "window_days"),
    )


class StockoutRisk(Base):
    """품절 위험 예측 — 공급사별 재고 소진 위험도."""
    __tablename__ = "stockout_risk"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    supplier_id: Mapped[str] = mapped_column(String(50), index=True)
    raw_id: Mapped[str] = mapped_column(String(200), default="")

    risk_score: Mapped[float] = mapped_column(Float, default=0.0)        # 0~100 (높을수록 위험)
    # LOW | MEDIUM | HIGH | CRITICAL
    risk_level: Mapped[str] = mapped_column(String(20), default="LOW", index=True)

    current_stock: Mapped[int] = mapped_column(Integer, default=0)
    avg_daily_sales: Mapped[float] = mapped_column(Float, default=0.0)
    days_until_stockout: Mapped[int] = mapped_column(Integer, default=999)  # 예상 품절 잔여 일수
    recent_stockout_count: Mapped[int] = mapped_column(Integer, default=0)  # 최근 30일 품절 횟수
    fulfillment_rate: Mapped[float] = mapped_column(Float, default=1.0)
    stock_trend: Mapped[str] = mapped_column(String(20), default="stable")  # rising|stable|falling|critical

    is_excluded: Mapped[bool] = mapped_column(default=False)              # 자동 제외 처리 여부
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_stockout_product_supplier", "product_id", "supplier_id"),
    )


class SeoRevision(Base):
    """기존 등록 상품의 SEO 재작성 제안 + 검수/반영 상태 추적.

    상태 흐름: DRAFT → REVIEW_PENDING → APPROVED|REJECTED → APPLIED|APPLY_FAILED
    쿠팡은 검증된 상품수정 API가 없어 APPROVED에서 멈추고 수동 반영(Excel) 안내로 대체한다.
    """
    __tablename__ = "seo_revisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)   # coupang | smartstore

    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    state_history: Mapped[str] = mapped_column(Text, default="[]")  # JSON [{status, ts}]

    # 원본 스냅샷 (비교/롤백용)
    original_name: Mapped[str] = mapped_column(String(300), default="")
    original_keywords: Mapped[str] = mapped_column(Text, default="[]")   # JSON list[str]
    original_detail_html: Mapped[str] = mapped_column(Text, default="")

    # AI 제안
    suggested_names: Mapped[str] = mapped_column(Text, default="[]")     # JSON list[str], A/B 후보
    suggested_keywords: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str], 30개+
    suggested_detail_html: Mapped[str] = mapped_column(Text, default="")
    competitor_summary: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    duplicate_of_product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # SEO 점수 (100점 만점: 제목20/키워드20/설명20/중복도10/CTR15/CVR15)
    score_before: Mapped[float] = mapped_column(Float, default=0.0)
    score_after: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[str] = mapped_column(Text, default="{}")     # JSON

    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(100), default="")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_seo_revisions_product_platform", "product_id", "platform"),
    )


_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = create_engine(
            f"sqlite:///{s.db_path}",
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
    return _engine


def _get_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal


@contextmanager
def get_db() -> Generator[Session, None, None]:
    db = _get_factory()()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(_get_engine())
