from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

from sqlalchemy import desc

from app.db import Listing, Order, Product, SupplierRawProduct, SupplierWorkflowItem, get_db
from app.sqlite_runtime import retry_sqlite_write
from app.seo.duplicate_detector import _normalize
from app.pricing.models import CategoryFeeRule, PriceChangeLog, PricingPolicy, ensure_pricing_schema


@dataclass
class PriceRow:
    listing_id: int
    product_id: int
    platform: str
    platform_id: str
    name: str
    source: str
    category: str
    supply_price: float
    supply_source: str
    current_price: float
    fee_rate: float
    fee_source: str
    current_margin_rate: float
    target_price: int
    delta: float
    auto_floor_price: int
    auto_ceiling_price: int
    eligible: bool
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_rate(value: float, default: float) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return default
    return rate if 0 <= rate < 0.60 else default


def calculate_target_price(
    supply_price: float,
    fee_rate: float,
    target_margin_rate: float = 0.36,
    rounding_unit: int = 900,
) -> int:
    cost = float(supply_price or 0)
    fee = float(fee_rate or 0)
    margin = float(target_margin_rate or 0)
    denominator = 1.0 - fee - margin
    if cost <= 0 or denominator <= 0.01:
        return 0
    raw = cost / denominator
    return round_price_up(raw, rounding_unit)


def round_price_up(value: float, ending: int = 900) -> int:
    value = max(10.0, float(value or 0))
    ending = int(ending or 0)
    if ending in (900, 500, 100):
        base = 1000
        if ending == 100:
            base = 100
            ending = 0
        if ending == 900:
            n = math.ceil((value - 900) / 1000)
            return max(900, int(n * 1000 + 900))
        if ending == 500:
            n = math.ceil((value - 500) / 1000)
            return max(500, int(n * 1000 + 500))
        return int(math.ceil(value / base) * base)
    if ending == 10:
        return int(math.ceil(value / 10.0) * 10)
    return int(math.ceil(value))


def margin_rate(price: float, supply_price: float, fee_rate: float) -> float:
    price = float(price or 0)
    if price <= 0:
        return 0.0
    return (price - float(supply_price or 0) - price * float(fee_rate or 0)) / price


def auto_price_bounds(
    base_price: int,
    supply_price: float,
    fee_rate: float,
    target_margin_rate: float,
    down_pct: float,
    up_pct: float,
    rounding_unit: int,
) -> tuple[int, int]:
    protected_floor = calculate_target_price(supply_price, fee_rate, target_margin_rate, rounding_unit)
    percentage_floor = round_price_up(base_price * (1 - max(0.0, down_pct) / 100.0), 10)
    ceiling = round_price_up(base_price * (1 + max(0.0, up_pct) / 100.0), 10)
    return max(protected_floor, percentage_floor), max(base_price, ceiling)


def get_policy() -> PricingPolicy:
    ensure_pricing_schema()
    with get_db() as db:
        row = db.query(PricingPolicy).filter_by(name="default").first()
        if row:
            db.expunge(row)
            return row
    def _create():
        with get_db() as db:
            row = PricingPolicy(name="default")
            db.add(row)
            db.commit()
            db.refresh(row)
            db.expunge(row)
            return row
    return retry_sqlite_write(_create, attempts=8)


def save_policy(
    *,
    target_margin_rate: float,
    coupang_fallback_fee_rate: float,
    smartstore_fallback_fee_rate: float,
    rounding_unit: int,
    coupang_auto_down_pct: float,
    coupang_auto_up_pct: float,
) -> None:
    ensure_pricing_schema()
    def _write():
        with get_db() as db:
            row = db.query(PricingPolicy).filter_by(name="default").first() or PricingPolicy(name="default")
            row.target_margin_rate = _safe_rate(target_margin_rate, 0.36)
            row.coupang_fallback_fee_rate = _safe_rate(coupang_fallback_fee_rate, 0.108)
            row.smartstore_fallback_fee_rate = _safe_rate(smartstore_fallback_fee_rate, 0.06)
            row.rounding_unit = int(rounding_unit)
            row.coupang_auto_down_pct = max(0.0, float(coupang_auto_down_pct))
            row.coupang_auto_up_pct = max(0.0, float(coupang_auto_up_pct))
            db.add(row)
            db.commit()
    retry_sqlite_write(_write, attempts=8)


def save_fee_rule(platform: str, category_key: str, fee_rate: float, note: str = "") -> None:
    ensure_pricing_schema()
    platform = str(platform).strip().lower()
    category_key = str(category_key).strip()
    rate = _safe_rate(fee_rate, -1)
    if not platform or not category_key or rate < 0:
        raise ValueError("플랫폼, 카테고리, 0~60% 미만 수수료율이 필요합니다.")
    def _write():
        with get_db() as db:
            row = (
                db.query(CategoryFeeRule)
                .filter_by(platform=platform, category_key=category_key)
                .order_by(desc(CategoryFeeRule.updated_at))
                .first()
            )
            if not row:
                row = CategoryFeeRule(platform=platform, category_key=category_key)
            row.fee_rate = rate
            row.note = str(note or "")[:300]
            row.source = "manual"
            db.add(row)
            db.commit()
    retry_sqlite_write(_write, attempts=8)


def list_fee_rules() -> list[dict[str, Any]]:
    ensure_pricing_schema()
    with get_db() as db:
        rows = db.query(CategoryFeeRule).order_by(CategoryFeeRule.platform, CategoryFeeRule.category_key).all()
        return [
            {
                "id": x.id,
                "platform": x.platform,
                "category_key": x.category_key,
                "fee_rate": x.fee_rate,
                "note": x.note,
            }
            for x in rows
        ]


def _resolve_supply_price(db, product: Product) -> tuple[float, str]:
    if float(product.supply_price or 0) > 0:
        return float(product.supply_price), f"상품 DB · {product.source}"

    raw = (
        db.query(SupplierRawProduct)
        .filter(SupplierRawProduct.product_id == product.id, SupplierRawProduct.raw_price > 0)
        .order_by(desc(SupplierRawProduct.updated_at))
        .first()
    )
    if raw:
        return float(raw.raw_price), f"도매 원본 · {raw.supplier_id}"

    workflow = (
        db.query(SupplierWorkflowItem)
        .filter(SupplierWorkflowItem.product_id == product.id, SupplierWorkflowItem.supply_price > 0)
        .order_by(desc(SupplierWorkflowItem.updated_at))
        .first()
    )
    if workflow:
        return float(workflow.supply_price), f"도매 워크플로우 · {workflow.supplier_id}"

    key = _normalize(product.name)
    if key:
        candidates = [
            p for p in db.query(Product).filter(Product.supply_price > 0).all()
            if p.id != product.id and _normalize(p.name) == key
        ]
        if len(candidates) == 1:
            return float(candidates[0].supply_price), f"동일 상품명 매칭 · {candidates[0].source}"
    return 0.0, "도매가 미확인"


def _resolve_fee_rate(
    db,
    product_id: int,
    platform: str,
    category: str,
    fallback: float,
) -> tuple[float, str]:
    order = (
        db.query(Order)
        .filter(
            Order.product_id == product_id,
            Order.platform == platform,
            Order.platform_fee_rate > 0,
        )
        .order_by(desc(Order.ordered_at))
        .first()
    )
    if order:
        return float(order.platform_fee_rate), "최근 실제 주문 수수료"

    rule = (
        db.query(CategoryFeeRule)
        .filter_by(platform=platform, category_key=str(category or "").strip())
        .order_by(desc(CategoryFeeRule.updated_at))
        .first()
    )
    if rule:
        return float(rule.fee_rate), "카테고리 수수료 규칙"

    return _safe_rate(fallback, 0.0), "플랫폼 fallback · 추정"


def _local_listing_records() -> list[dict[str, Any]]:
    with get_db() as db:
        out = []
        listings = (
            db.query(Listing)
            .filter(Listing.status == "success", Listing.platform.in_(["coupang", "smartstore"]))
            .order_by(Listing.platform, Listing.id)
            .all()
        )
        for listing in listings:
            p = db.get(Product, listing.product_id)
            if not p:
                continue
            supply, source = _resolve_supply_price(db, p)
            out.append({
                "listing_id": listing.id,
                "product_id": p.id,
                "platform": listing.platform,
                "platform_id": listing.platform_id,
                "name": p.name,
                "source": p.source,
                "local_category": p.category,
                "local_price": float(p.sell_price or 0),
                "supply_price": supply,
                "supply_source": source,
            })
        return out


def _fetch_coupang_prices(platform_ids: set[str]) -> dict[str, dict[str, Any]]:
    from app.platforms.coupang import get_coupang_uploader
    uploader = get_coupang_uploader()
    result: dict[str, dict[str, Any]] = {}
    for pid in platform_ids:
        try:
            detail = uploader.get_seller_product(pid) or {}
            prices = [
                float(x.get("salePrice") or 0)
                for x in detail.get("items", [])
                if float(x.get("salePrice") or 0) > 0
            ]
            result[pid] = {
                "price": min(prices) if prices else 0.0,
                "category": str(detail.get("displayCategoryCode") or ""),
                "error": "",
            }
        except Exception as exc:
            result[pid] = {"price": 0.0, "category": "", "error": str(exc)}
    return result


def _fetch_smartstore_prices(platform_ids: set[str]) -> dict[str, dict[str, Any]]:
    from app.sync.catalog_sync import _smartstore_search_page
    from app.platforms.smartstore import get_smartstore_uploader
    uploader = get_smartstore_uploader()
    result: dict[str, dict[str, Any]] = {}
    for page in range(1, 51):
        data = _smartstore_search_page(uploader, page, 500)
        contents = data.get("contents") or []
        if not contents:
            break
        for row in contents:
            origin_no = str(row.get("originProductNo") or "").strip()
            channels = row.get("channelProducts") or []
            channel = next((x for x in channels if x.get("channelServiceType") == "STOREFARM"), channels[0] if channels else {})
            if not origin_no:
                origin_no = str(channel.get("originProductNo") or "").strip()
            if origin_no in platform_ids:
                result[origin_no] = {
                    "price": float(channel.get("salePrice") or row.get("salePrice") or 0),
                    "category": str(channel.get("categoryId") or channel.get("wholeCategoryName") or ""),
                    "error": "",
                }
        if platform_ids.issubset(result.keys()):
            break
        total_pages = int(data.get("totalPages") or 0)
        if data.get("last") is True or (total_pages and page >= total_pages):
            break
    return result


def load_price_rows(*, live: bool = True) -> list[PriceRow]:
    ensure_pricing_schema()
    policy = get_policy()
    local = _local_listing_records()
    by_platform: dict[str, dict[str, dict[str, Any]]] = {"coupang": {}, "smartstore": {}}
    if live:
        coupang_ids = {x["platform_id"] for x in local if x["platform"] == "coupang" and x["platform_id"]}
        naver_ids = {x["platform_id"] for x in local if x["platform"] == "smartstore" and x["platform_id"]}
        if coupang_ids:
            by_platform["coupang"] = _fetch_coupang_prices(coupang_ids)
        if naver_ids:
            by_platform["smartstore"] = _fetch_smartstore_prices(naver_ids)

    rows: list[PriceRow] = []
    with get_db() as db:
        for x in local:
            remote = by_platform.get(x["platform"], {}).get(x["platform_id"], {})
            current_price = float(remote.get("price") or x["local_price"] or 0)
            category = str(remote.get("category") or x["local_category"] or "")
            fallback = (
                policy.coupang_fallback_fee_rate
                if x["platform"] == "coupang"
                else policy.smartstore_fallback_fee_rate
            )
            fee, fee_source = _resolve_fee_rate(db, x["product_id"], x["platform"], category, fallback)
            target = calculate_target_price(
                x["supply_price"], fee, policy.target_margin_rate, policy.rounding_unit
            )
            floor, ceiling = (0, 0)
            if x["platform"] == "coupang" and target:
                floor, ceiling = auto_price_bounds(
                    target,
                    x["supply_price"],
                    fee,
                    policy.target_margin_rate,
                    policy.coupang_auto_down_pct,
                    policy.coupang_auto_up_pct,
                    policy.rounding_unit,
                )
            warning = str(remote.get("error") or "")
            if x["supply_price"] <= 0:
                warning = "도매가 미확인"
            elif current_price <= 0:
                warning = warning or "현재 판매가 미확인"
            eligible = x["supply_price"] > 0 and current_price > 0 and target > 0 and 0 <= fee < 0.60
            rows.append(PriceRow(
                listing_id=x["listing_id"],
                product_id=x["product_id"],
                platform=x["platform"],
                platform_id=x["platform_id"],
                name=x["name"],
                source=x["source"],
                category=category,
                supply_price=x["supply_price"],
                supply_source=x["supply_source"],
                current_price=current_price,
                fee_rate=fee,
                fee_source=fee_source,
                current_margin_rate=margin_rate(current_price, x["supply_price"], fee),
                target_price=target,
                delta=target - current_price if target else 0,
                auto_floor_price=floor,
                auto_ceiling_price=ceiling,
                eligible=eligible,
                warning=warning,
            ))
    return rows


def _log_change(row: dict[str, Any], status: str, error: str = "") -> None:
    ensure_pricing_schema()
    def _write():
        with get_db() as db:
            db.add(PriceChangeLog(
                product_id=int(row["product_id"]),
                listing_id=int(row["listing_id"]),
                platform=str(row["platform"]),
                platform_id=str(row["platform_id"]),
                supply_price=float(row["supply_price"]),
                fee_rate=float(row["fee_rate"]),
                target_margin_rate=float(row["target_margin_rate"]),
                before_price=float(row["before_price"]),
                after_price=float(row["after_price"]),
                status=status,
                error=str(error or "")[:1000],
            ))
            db.commit()
    retry_sqlite_write(_write, attempts=8)


def apply_price(row: PriceRow, new_price: int | None = None) -> dict[str, Any]:
    price = int(new_price or row.target_price)
    payload = {
        **row.to_dict(),
        "target_margin_rate": get_policy().target_margin_rate,
        "before_price": row.current_price,
        "after_price": price,
    }
    if not row.eligible or price <= 0:
        msg = row.warning or "가격 적용 조건을 충족하지 않습니다."
        _log_change(payload, "skipped", msg)
        return {"ok": False, "error": msg, "listing_id": row.listing_id}

    # Remote mutation is called exactly once. DB logging may retry independently.
    try:
        if row.platform == "coupang":
            from app.platforms.coupang import get_coupang_uploader
            result = get_coupang_uploader().update_price(row.platform_id, price)
        elif row.platform == "smartstore":
            from app.platforms.smartstore import get_smartstore_uploader
            result = get_smartstore_uploader().update_price(row.platform_id, price)
        else:
            result = {"ok": False, "error": "지원하지 않는 판매처"}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}

    if result.get("ok"):
        _log_change(payload, "success")
        return {"ok": True, "listing_id": row.listing_id, "price": price}
    error = str(result.get("error") or "가격 수정 실패")
    _log_change(payload, "failed", error)
    return {"ok": False, "listing_id": row.listing_id, "error": error}


def apply_many(rows: list[PriceRow]) -> dict[str, Any]:
    results = [apply_price(row) for row in rows]
    return {
        "total": len(results),
        "success": sum(1 for x in results if x.get("ok")),
        "failed": sum(1 for x in results if not x.get("ok")),
        "results": results,
    }


def price_change_history(limit: int = 200) -> list[dict[str, Any]]:
    ensure_pricing_schema()
    with get_db() as db:
        rows = db.query(PriceChangeLog).order_by(desc(PriceChangeLog.created_at)).limit(limit).all()
        return [
            {
                "시각": x.created_at,
                "플랫폼": x.platform,
                "상품ID": x.product_id,
                "판매처ID": x.platform_id,
                "도매가": x.supply_price,
                "수수료율": x.fee_rate,
                "목표마진": x.target_margin_rate,
                "변경전": x.before_price,
                "변경후": x.after_price,
                "상태": x.status,
                "오류": x.error,
            }
            for x in rows
        ]
