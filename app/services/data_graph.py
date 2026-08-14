"""AutoSellerAI 데이터 관계 그래프.

Product를 기준 마스터로 두고 공급처 원본, 공급처 워크플로, 판매채널 Listing,
판매채널별 세부 식별자, 주문, 정산/성과 데이터를 서로 연결한다.

특히 쿠팡은 Listing.platform_id가 sellerProductId인데 주문은 vendorItemId로 들어오므로
별도의 MarketplaceIdentity 테이블로 sellerProductId/vendorItemId를 같은 Product에 연결한다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Index
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.db import (
    Base,
    Listing,
    Order,
    PlatformOrder,
    Product,
    ProductPerformance,
    SupplierRawProduct,
    SupplierWorkflowItem,
    get_db,
    _get_engine,
)


class MarketplaceIdentity(Base):
    __tablename__ = "marketplace_identities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    listing_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    identity_type: Mapped[str] = mapped_column(String(50), index=True)
    identity_value: Mapped[str] = mapped_column(String(220), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index(
            "ux_market_identity",
            "platform", "identity_type", "identity_value",
            unique=True,
        ),
    )


def ensure_data_graph_schema() -> None:
    MarketplaceIdentity.__table__.create(_get_engine(), checkfirst=True)


def _upsert_identity(db, *, product_id: int, listing_id: int | None,
                     platform: str, identity_type: str, identity_value: Any) -> bool:
    """원자적으로 marketplace identity를 생성/갱신한다.

    order_sync와 data_reconcile처럼 여러 worker가 같은 identity를 동시에 발견해도
    SELECT -> INSERT race로 UNIQUE constraint 오류가 발생하지 않아야 한다.
    SQLite/PostgreSQL은 DB native UPSERT를 사용하고, 기타 DB는 SAVEPOINT 기반
    fallback으로 기존 행을 재사용한다.
    """
    value = str(identity_value or "").strip()
    if not value:
        return False

    values = {
        "product_id": int(product_id),
        "listing_id": int(listing_id) if listing_id else None,
        "platform": str(platform),
        "identity_type": str(identity_type),
        "identity_value": value,
        "updated_at": datetime.utcnow(),
    }
    dialect = (db.get_bind().dialect.name or "").lower()

    # Native UPSERT is one DB statement, so concurrent workers cannot both win an INSERT.
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert

        stmt = dialect_insert(MarketplaceIdentity).values(**values)
        update_values: dict[str, Any] = {
            "product_id": stmt.excluded.product_id,
            "updated_at": stmt.excluded.updated_at,
        }
        if listing_id:
            update_values["listing_id"] = stmt.excluded.listing_id
        stmt = stmt.on_conflict_do_update(
            index_elements=["platform", "identity_type", "identity_value"],
            set_=update_values,
        )
        db.execute(stmt)
        return True

    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert

        stmt = dialect_insert(MarketplaceIdentity).values(**values)
        update_values = {
            "product_id": stmt.excluded.product_id,
            "updated_at": stmt.excluded.updated_at,
        }
        if listing_id:
            update_values["listing_id"] = stmt.excluded.listing_id
        stmt = stmt.on_conflict_do_update(
            index_elements=["platform", "identity_type", "identity_value"],
            set_=update_values,
        )
        db.execute(stmt)
        return True

    # Conservative fallback for an unsupported SQL dialect.  A nested transaction
    # keeps a duplicate-key race from poisoning the caller's whole reconciliation.
    row = db.query(MarketplaceIdentity).filter_by(
        platform=platform,
        identity_type=identity_type,
        identity_value=value,
    ).first()
    if row:
        changed = row.product_id != product_id or bool(listing_id and row.listing_id != listing_id)
        row.product_id = product_id
        if listing_id:
            row.listing_id = listing_id
        return changed

    try:
        with db.begin_nested():
            db.add(MarketplaceIdentity(
                product_id=product_id,
                listing_id=listing_id,
                platform=platform,
                identity_type=identity_type,
                identity_value=value,
            ))
            db.flush()
        return True
    except IntegrityError:
        # Another transaction inserted the same identity between our SELECT/INSERT.
        row = db.query(MarketplaceIdentity).filter_by(
            platform=platform,
            identity_type=identity_type,
            identity_value=value,
        ).first()
        if not row:
            raise
        row.product_id = product_id
        if listing_id:
            row.listing_id = listing_id
        return True


def _seed_listing_identities(db) -> int:
    changed = 0
    for listing in db.query(Listing).filter(Listing.status == "success").all():
        identity_type = "seller_product_id" if listing.platform == "coupang" else "origin_product_no"
        changed += int(_upsert_identity(
            db,
            product_id=listing.product_id,
            listing_id=listing.id,
            platform=listing.platform,
            identity_type=identity_type,
            identity_value=listing.platform_id,
        ))
    return changed


def _fetch_coupang_identities(db) -> tuple[int, list[str]]:
    changed = 0
    errors: list[str] = []
    try:
        from app.platforms.coupang import get_coupang_uploader, reset_coupang_uploader
        reset_coupang_uploader()
        uploader = get_coupang_uploader()
    except Exception as exc:
        return 0, [f"쿠팡 초기화 실패: {exc}"]

    listings = db.query(Listing).filter_by(platform="coupang", status="success").all()
    for listing in listings:
        seller_product_id = str(listing.platform_id or "").strip()
        if not seller_product_id:
            continue
        try:
            detail = uploader.get_seller_product(seller_product_id) or {}
            changed += int(_upsert_identity(
                db,
                product_id=listing.product_id,
                listing_id=listing.id,
                platform="coupang",
                identity_type="seller_product_id",
                identity_value=seller_product_id,
            ))
            for item in detail.get("items") or []:
                changed += int(_upsert_identity(
                    db,
                    product_id=listing.product_id,
                    listing_id=listing.id,
                    platform="coupang",
                    identity_type="vendor_item_id",
                    identity_value=item.get("vendorItemId"),
                ))
                changed += int(_upsert_identity(
                    db,
                    product_id=listing.product_id,
                    listing_id=listing.id,
                    platform="coupang",
                    identity_type="seller_product_item_id",
                    identity_value=item.get("sellerProductItemId"),
                ))
        except Exception as exc:
            errors.append(f"쿠팡 sellerProductId={seller_product_id}: {exc}")
    return changed, errors


def _fetch_smartstore_identities(db) -> tuple[int, list[str]]:
    changed = 0
    errors: list[str] = []
    try:
        from app.platforms.smartstore import get_smartstore_uploader, reset_smartstore_uploader
        from app.sync.catalog_sync import _smartstore_search_page
        reset_smartstore_uploader()
        uploader = get_smartstore_uploader()
        for page in range(1, 21):
            data = _smartstore_search_page(uploader, page=page, page_size=500)
            contents = data.get("contents") or []
            if not contents:
                break
            for row in contents:
                origin_no = str(row.get("originProductNo") or "").strip()
                channels = row.get("channelProducts") or []
                channel = next(
                    (x for x in channels if x.get("channelServiceType") == "STOREFARM"),
                    channels[0] if channels else {},
                )
                if not origin_no:
                    origin_no = str(channel.get("originProductNo") or "").strip()
                listing = db.query(Listing).filter_by(
                    platform="smartstore", platform_id=origin_no, status="success"
                ).first()
                if not listing:
                    continue
                changed += int(_upsert_identity(
                    db,
                    product_id=listing.product_id,
                    listing_id=listing.id,
                    platform="smartstore",
                    identity_type="origin_product_no",
                    identity_value=origin_no,
                ))
                changed += int(_upsert_identity(
                    db,
                    product_id=listing.product_id,
                    listing_id=listing.id,
                    platform="smartstore",
                    identity_type="channel_product_no",
                    identity_value=channel.get("channelProductNo"),
                ))
            total_pages = int(data.get("totalPages") or 0)
            if data.get("last") is True or (total_pages and page >= total_pages):
                break
    except Exception as exc:
        errors.append(f"스마트스토어 식별자 조회 실패: {exc}")
    return changed, errors


def _link_supplier_data(db) -> dict[str, int]:
    raw_linked = workflow_linked = 0
    products = db.query(Product).all()
    product_by_source = {
        (str(p.source or ""), str(p.source_id or "")): p.id
        for p in products if p.source and p.source_id
    }

    raw_rows = db.query(SupplierRawProduct).all()
    raw_by_key: dict[tuple[str, str], SupplierRawProduct] = {}
    for raw in raw_rows:
        key = (str(raw.supplier_id or ""), str(raw.raw_id or ""))
        raw_by_key[key] = raw
        product_id = product_by_source.get(key)
        if product_id and raw.product_id != product_id:
            raw.product_id = product_id
            raw_linked += 1

    for wf in db.query(SupplierWorkflowItem).all():
        key = (str(wf.supplier_id or ""), str(wf.raw_id or ""))
        raw = raw_by_key.get(key)
        if raw and wf.raw_product_id != raw.id:
            wf.raw_product_id = raw.id
            workflow_linked += 1
        product_id = product_by_source.get(key)
        if product_id and wf.product_id != product_id:
            wf.product_id = product_id
            workflow_linked += 1

    return {"supplier_raw_linked": raw_linked, "supplier_workflow_linked": workflow_linked}


def _resolve_identity_product(db, platform: str, identity_type: str, value: str) -> int | None:
    if not value:
        return None
    row = db.query(MarketplaceIdentity).filter_by(
        platform=platform,
        identity_type=identity_type,
        identity_value=str(value),
    ).first()
    return row.product_id if row else None


def _unique_name_fallback(db, order: PlatformOrder) -> int | None:
    """식별자가 없는 과거 주문만 보수적으로 이름 정확 일치로 연결한다."""
    name = str(order.product_name or "").strip()
    if not name:
        return None
    candidate_ids = [x.product_id for x in db.query(Listing).filter_by(
        platform=order.platform, status="success"
    ).all()]
    if not candidate_ids:
        return None
    matches = db.query(Product).filter(Product.id.in_(candidate_ids), Product.name == name).all()
    return matches[0].id if len(matches) == 1 else None


def _link_platform_orders(db) -> int:
    linked = 0
    for order in db.query(PlatformOrder).all():
        resolved: int | None = None
        if order.platform == "coupang":
            resolved = _resolve_identity_product(db, "coupang", "vendor_item_id", str(order.vendor_item_id or ""))
        elif order.platform == "smartstore":
            resolved = _resolve_identity_product(db, "smartstore", "origin_product_no", str(order.origin_product_no or ""))
            if not resolved:
                resolved = _resolve_identity_product(db, "smartstore", "channel_product_no", str(order.platform_item_id or ""))

        if not resolved:
            # 레거시 데이터 호환: Listing.platform_id와 직접 같은 경우
            lookup_value = str(order.origin_product_no or order.vendor_item_id or "").strip()
            if lookup_value:
                listing = db.query(Listing).filter_by(
                    platform=order.platform, platform_id=lookup_value, status="success"
                ).first()
                resolved = listing.product_id if listing else None
        if not resolved:
            resolved = _unique_name_fallback(db, order)

        if resolved and order.product_id != resolved:
            order.product_id = resolved
            linked += 1
    return linked


def _link_financial_and_performance(db) -> dict[str, int]:
    financial = performance = 0
    for row in db.query(Order).all():
        if not row.platform_order_id:
            continue
        platform_order = db.query(PlatformOrder).filter_by(
            platform=row.platform,
            platform_order_id=row.platform_order_id,
        ).first()
        if platform_order and platform_order.product_id and row.product_id != platform_order.product_id:
            row.product_id = platform_order.product_id
            financial += 1

    for perf in db.query(ProductPerformance).all():
        if perf.listing_id:
            continue
        listing = db.query(Listing).filter_by(
            product_id=perf.product_id,
            platform=perf.platform,
            status="success",
        ).first()
        if listing:
            perf.listing_id = listing.id
            performance += 1
    return {"financial_linked": financial, "performance_linked": performance}


def get_data_graph_health() -> dict[str, int]:
    ensure_data_graph_schema()
    with get_db() as db:
        return {
            "products": db.query(Product).count(),
            "listings": db.query(Listing).count(),
            "marketplace_identities": db.query(MarketplaceIdentity).count(),
            "platform_orders": db.query(PlatformOrder).count(),
            "unlinked_platform_orders": db.query(PlatformOrder).filter(PlatformOrder.product_id.is_(None)).count(),
            "supplier_raw_unlinked": db.query(SupplierRawProduct).filter(SupplierRawProduct.product_id.is_(None)).count(),
            "workflow_unlinked": db.query(SupplierWorkflowItem).filter(SupplierWorkflowItem.product_id.is_(None)).count(),
        }


def reconcile_data_graph(*, fetch_remote_identities: bool = False) -> dict[str, Any]:
    """관련 데이터의 논리 연결을 복구/갱신한다. 외부 API에는 읽기만 수행한다."""
    ensure_data_graph_schema()
    errors: list[str] = []
    with get_db() as db:
        identity_changes = _seed_listing_identities(db)
        if fetch_remote_identities:
            cp_changed, cp_errors = _fetch_coupang_identities(db)
            ss_changed, ss_errors = _fetch_smartstore_identities(db)
            identity_changes += cp_changed + ss_changed
            errors.extend(cp_errors + ss_errors)

        supplier = _link_supplier_data(db)
        platform_orders_linked = _link_platform_orders(db)
        downstream = _link_financial_and_performance(db)
        db.commit()

    return {
        "ok": True,
        "identity_changes": identity_changes,
        "platform_orders_linked": platform_orders_linked,
        **supplier,
        **downstream,
        "health": get_data_graph_health(),
        "errors": errors,
    }
