"""파이프라인 — 공급처 수집 → AI 최적화 → DB 저장 → 플랫폼 업로드."""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timedelta

from app.db import (
    get_db, init_db, Product, Listing, MarketInsight,
    Order, SettlementPeriod, TaxSummary,
    Inventory, PurchaseOrder, PurchaseOrderItem, StockMovement,
    NotificationLog, ScheduledJob, JobRunLog,
    CircuitBreakerState, HealthCheckLog, PlatformOrder,
    SupplierRawProduct, SupplierWorkflowItem,
)

logger = logging.getLogger(__name__)


# ── DB 초기화 (앱 시작 시 호출) ───────────────────────────────────────────────

def setup():
    os.makedirs("data", exist_ok=True)
    init_db()


# ── 상품 수집 → DB 저장 ───────────────────────────────────────────────────────

def import_product(source: str, source_id: str,
                   sell_price: float, ai_enhance: bool = True) -> dict:
    """공급처에서 상품 수집 → AI 최적화 → DB 저장.

    Returns:
        {"id": int, "sku": str, "name": str, "status": "imported" | "updated" | "error", "error": str}
    """
    try:
        # 어댑터 레지스트리 → NormalizedProduct 조회
        from app.suppliers.registry import get_adapter
        adapter = get_adapter(source)
        if adapter:
            normalized = adapter.get_product(source_id)
            if not normalized:
                return {"status": "error", "error": "상품 수집 실패 — 공급처에서 상품을 가져오지 못했습니다"}
            # NormalizedProduct를 레거시 prod 인터페이스로 변환
            class _ProdProxy:
                pass
            prod = _ProdProxy()
            prod.source_id = normalized.raw_id
            prod.source_url = normalized.raw_url
            prod.name = normalized.name
            prod.supply_price = normalized.supply_price
            prod.category = normalized.category
            prod.brand = normalized.brand
            prod.origin = normalized.origin
            prod.material = normalized.material
            prod.images = normalized.images
            prod.detail_images = normalized.detail_images
            prod.options = normalized.options
        else:
            # 레거시 폴백 (어댑터 미등록 공급사)
            if source == "domeggook":
                from app.suppliers.domeggook import get_product
                prod = get_product(source_id)
            elif source == "domemai":
                from app.suppliers.domemai import get_product as _get_dm
                prod = _get_dm(source_id)
            elif source == "onchannel":
                from app.suppliers.onchannel import get_product
                prod = get_product(source_id)
            else:
                return {"status": "error", "error": f"알 수 없는 공급처: {source}"}

        if not prod:
            return {"status": "error", "error": "상품 수집 실패 — 공급처에서 상품을 가져오지 못했습니다"}

        if ai_enhance:
            from app.ai import optimize_product
            ai = optimize_product(
                prod.name, prod.category, prod.options,
                prod.origin, prod.material,
            )
            name = ai["name"]
            detail_html = ai["detail_html"]
        else:
            name = prod.name
            detail_html = ""

        sku = f"{source[:3].upper()}-{source_id}"

        with get_db() as db:
            existing = db.query(Product).filter_by(sku=sku).first()
            if existing:
                existing.sell_price = sell_price
                existing.detail_html = detail_html
                existing.name = name
                db.commit()
                return {"id": existing.id, "sku": sku, "name": name, "status": "updated"}

            p = Product(
                sku=sku,
                source=source,
                source_id=source_id,
                source_url=prod.source_url,
                name=name,
                supply_price=prod.supply_price,
                sell_price=sell_price,
                category=prod.category,
                brand=prod.brand,
                origin=prod.origin,
                material=prod.material,
                images=json.dumps(prod.images, ensure_ascii=False),
                detail_images=json.dumps(prod.detail_images, ensure_ascii=False),
                options=json.dumps(prod.options, ensure_ascii=False),
                detail_html=detail_html,
                status="ready",
            )
            db.add(p)
            db.commit()
            db.refresh(p)
            return {"id": p.id, "sku": sku, "name": name, "status": "imported"}

    except Exception as exc:
        logger.error("import_product 실패: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}


# ── 플랫폼 업로드 ─────────────────────────────────────────────────────────────

def upload_product(product_id: int, platforms: list[str]) -> list[dict]:
    """DB 상품 → 지정 플랫폼들에 업로드.

    Returns:
        [{"platform": str, "status": "success"|"failed", "platform_id": str, "error": str}]
    """
    # 업로더 싱글턴이 오래된 설정을 참조하지 않도록 매 업로드 시 갱신
    from app.platforms.coupang import reset_coupang_uploader
    from app.platforms.smartstore import reset_smartstore_uploader
    reset_coupang_uploader()
    reset_smartstore_uploader()

    results = []

    with get_db() as db:
        p = db.query(Product).filter_by(id=product_id).first()
        if not p:
            return [{"platform": pl, "status": "failed", "error": "상품 없음"} for pl in platforms]

        prod_dict = {
            "sku": p.sku,
            "name": p.name,
            "sell_price": float(p.sell_price),
            "supply_price": float(p.supply_price),
            "stock": 999,
            "category": p.category,
            "brand": p.brand,
            "origin": p.origin,
            "images": json.loads(p.images or "[]"),
            "detail_images": json.loads(p.detail_images or "[]"),
            "options": json.loads(p.options or "[]"),
            "detail_html": p.detail_html or "",
            "shipping_fee": 3000,
            "return_fee": 3000,
        }

        from app.hardening.circuit_breaker import get_circuit_breaker, CircuitOpenError
        from app.hardening.rate_limiter import get_rate_limiter

        for platform in platforms:
            try:
                svc = "smartstore_api" if platform == "smartstore" else "coupang_api"
                cb  = get_circuit_breaker(svc)
                rl  = get_rate_limiter(svc)

                if not rl.acquire(timeout=8):
                    results.append({"platform": platform, "status": "failed",
                                    "error": "Rate limit — 잠시 후 재시도", "platform_id": ""})
                    continue

                if platform == "smartstore":
                    from app.platforms.smartstore import get_smartstore_uploader
                    res = cb.call(lambda: get_smartstore_uploader().create_product(prod_dict))
                    platform_id = str(res.get("originProductNo", ""))
                elif platform == "coupang":
                    from app.platforms.coupang import get_coupang_uploader
                    res = cb.call(lambda: get_coupang_uploader().create_product(prod_dict))
                    platform_id = str(res.get("data", {}).get("sellerProductId", ""))
                else:
                    results.append({"platform": platform, "status": "failed",
                                    "error": f"알 수 없는 플랫폼: {platform}"})
                    continue

                listing = Listing(product_id=product_id, platform=platform,
                                  platform_id=platform_id, status="success")
                db.add(listing)
                if p.status != "listed":
                    p.status = "listed"
                db.commit()
                results.append({"platform": platform, "status": "success",
                                 "platform_id": platform_id, "error": ""})
                _notify_upload_success(platform, p.name, platform_id)

            except CircuitOpenError as exc:
                err = str(exc)
                results.append({"platform": platform, "status": "failed",
                                 "platform_id": "", "error": err})
                logger.warning("업로드 Circuit OPEN [%s]: %s", platform, err)
            except Exception as exc:
                err = str(exc)
                listing = Listing(product_id=product_id, platform=platform,
                                  status="failed", error=err[:500])
                db.add(listing)
                db.commit()
                logger.error("업로드 실패 [%s/%s]: %s", platform, p.sku, err)
                results.append({"platform": platform, "status": "failed",
                                 "platform_id": "", "error": err})
                _notify_upload_failed(platform, p.name, err)

    return results


# ── 상품 목록 조회 ────────────────────────────────────────────────────────────

def list_products(status: str = "", page: int = 1, limit: int = 100) -> dict:
    with get_db() as db:
        q = db.query(Product)
        if status:
            q = q.filter(Product.status == status)
        total = q.count()
        items = q.order_by(Product.id.desc()).offset((page - 1) * limit).limit(limit).all()
        return {
            "total": total,
            "items": [_product_to_dict(p) for p in items],
        }


def get_product_detail(product_id: int) -> dict | None:
    with get_db() as db:
        p = db.query(Product).filter_by(id=product_id).first()
        if not p:
            return None
        listings = db.query(Listing).filter_by(product_id=product_id).all()
        d = _product_to_dict(p, full=True)
        d["listings"] = [
            {"platform": l.platform, "status": l.status,
             "platform_id": l.platform_id, "error": l.error[:100] if l.error else ""}
            for l in listings
        ]
        return d


def delete_product(product_id: int) -> bool:
    with get_db() as db:
        p = db.query(Product).filter_by(id=product_id).first()
        if not p:
            return False
        db.query(Listing).filter_by(product_id=product_id).delete()
        db.delete(p)
        db.commit()
    return True


def get_stats() -> dict:
    with get_db() as db:
        total = db.query(Product).count()
        ready = db.query(Product).filter_by(status="ready").count()
        listed = db.query(Product).filter_by(status="listed").count()
        ss_ok = db.query(Listing).filter_by(platform="smartstore", status="success").count()
        cp_ok = db.query(Listing).filter_by(platform="coupang", status="success").count()
        failed = db.query(Listing).filter_by(status="failed").count()
    return {
        "products": {"total": total, "ready": ready, "listed": listed},
        "uploads": {"smartstore": ss_ok, "coupang": cp_ok, "failed": failed},
    }


# ── 시장 분석 (Market Intelligence) ─────────────────────────────────────────────

def analyze_market(keyword: str, force_refresh: bool = False) -> dict:
    """Market Intelligence Engine — 네이버 트렌드 + 쿠팡 베스트 + Claude 기회점수.

    24시간 이내 캐시가 있으면 DB에서 반환, 없으면 새로 수집·분석 후 저장.

    Returns:
        {
          "keyword": str,
          "trend_data": [{period, ratio}],
          "shopping_stats": {total_items, avg_price, min_price, max_price, top_brands},
          "coupang_best": [{rank, name, price, rating, review_count, badge}],
          "opportunity_score": int,
          "score_breakdown": {trend, competition, margin, demand},
          "recommendation": str,
          "tags": [str],
          "risk_factors": [str],
          "cached": bool,
          "analyzed_at": str,
        }
    """
    # 캐시 확인 (24시간)
    if not force_refresh:
        cached = _get_cached_insight(keyword)
        if cached:
            return cached

    # 데이터 수집
    from app.market.naver_datalab import get_search_trend, get_shopping_stats
    from app.market.coupang_best import get_best_items
    from app.market.opportunity_score import calculate_opportunity_score

    trend_data = get_search_trend(keyword, months=12)
    shopping_stats = get_shopping_stats(keyword)
    coupang_best = get_best_items(keyword, limit=10)

    # Claude 기회점수
    score_result = calculate_opportunity_score(keyword, trend_data, shopping_stats, coupang_best)

    # DB 저장
    trend_json = json.dumps([{"period": t.period, "ratio": t.ratio} for t in trend_data], ensure_ascii=False)
    stats_json = json.dumps({
        "total_items": shopping_stats.total_items,
        "avg_price": shopping_stats.avg_price,
        "min_price": shopping_stats.min_price,
        "max_price": shopping_stats.max_price,
        "top_brands": shopping_stats.top_brands,
        "sample_items": shopping_stats.sample_items,
    }, ensure_ascii=False)
    best_json = json.dumps([{
        "rank": b.rank, "name": b.name, "price": b.price,
        "rating": b.rating, "review_count": b.review_count, "badge": b.badge,
    } for b in coupang_best], ensure_ascii=False)

    now = datetime.utcnow()
    with get_db() as db:
        insight = MarketInsight(
            keyword=keyword,
            trend_data=trend_json,
            shopping_stats=stats_json,
            coupang_best=best_json,
            opportunity_score=score_result.get("score", 0),
            score_breakdown=json.dumps(score_result.get("breakdown", {}), ensure_ascii=False),
            recommendation=score_result.get("recommendation", ""),
            tags=json.dumps(score_result.get("tags", []), ensure_ascii=False),
            risk_factors=json.dumps(score_result.get("risk_factors", []), ensure_ascii=False),
            analyzed_at=now,
        )
        db.add(insight)
        db.commit()

    return {
        "keyword": keyword,
        "trend_data": json.loads(trend_json),
        "shopping_stats": json.loads(stats_json),
        "coupang_best": json.loads(best_json),
        "opportunity_score": score_result.get("score", 0),
        "score_breakdown": score_result.get("breakdown", {}),
        "recommendation": score_result.get("recommendation", ""),
        "tags": score_result.get("tags", []),
        "risk_factors": score_result.get("risk_factors", []),
        "cached": False,
        "analyzed_at": now.isoformat(),
    }


def get_market_history(limit: int = 20) -> list[dict]:
    """최근 분석한 키워드 목록 반환."""
    with get_db() as db:
        rows = (
            db.query(MarketInsight)
            .order_by(MarketInsight.analyzed_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "keyword": r.keyword,
                "opportunity_score": r.opportunity_score,
                "tags": json.loads(r.tags or "[]"),
                "analyzed_at": r.analyzed_at.isoformat() if r.analyzed_at else "",
            }
            for r in rows
        ]


def _get_cached_insight(keyword: str) -> dict | None:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    with get_db() as db:
        row = (
            db.query(MarketInsight)
            .filter(
                MarketInsight.keyword == keyword,
                MarketInsight.analyzed_at >= cutoff,
            )
            .order_by(MarketInsight.analyzed_at.desc())
            .first()
        )
        if not row:
            return None
        return {
            "keyword": row.keyword,
            "trend_data": json.loads(row.trend_data or "[]"),
            "shopping_stats": json.loads(row.shopping_stats or "{}"),
            "coupang_best": json.loads(row.coupang_best or "[]"),
            "opportunity_score": row.opportunity_score,
            "score_breakdown": json.loads(row.score_breakdown or "{}"),
            "recommendation": row.recommendation,
            "tags": json.loads(row.tags or "[]"),
            "risk_factors": json.loads(row.risk_factors or "[]"),
            "cached": True,
            "analyzed_at": row.analyzed_at.isoformat() if row.analyzed_at else "",
        }


# ── 내부 ──────────────────────────────────────────────────────────────────────

# ── 정산 엔진 (Settlement Engine) ────────────────────────────────────────────

def add_order(
    product_id: int,
    platform: str,
    unit_sale_price: float,
    quantity: int = 1,
    shipping_fee_paid: float = 3000,
    shipping_fee_charged: float = 0,
    ad_cost: float = 0,
    return_cost: float = 0,
    platform_order_id: str = "",
    status: str = "completed",
    ordered_at: datetime | None = None,
    memo: str = "",
) -> dict:
    """주문 1건을 등록하고 순이익을 계산한다."""
    from app.settlement.calculator import calculate_order_profit, PLATFORM_FEE_RATES

    with get_db() as db:
        p = db.query(Product).filter_by(id=product_id).first()
        if not p:
            return {"status": "error", "error": "상품 없음"}

        unit_supply_price = float(p.supply_price)
        rates = PLATFORM_FEE_RATES.get(platform, {})
        fee_rate = rates.get("default", 0.108)

        result = calculate_order_profit(
            platform=platform,
            unit_sale_price=unit_sale_price,
            unit_supply_price=unit_supply_price,
            quantity=quantity,
            shipping_fee_paid=shipping_fee_paid,
            shipping_fee_charged=shipping_fee_charged,
            platform_fee_rate=fee_rate,
            ad_cost=ad_cost,
            return_cost=return_cost,
        )

        order = Order(
            product_id=product_id,
            platform=platform,
            platform_order_id=platform_order_id,
            quantity=quantity,
            unit_sale_price=unit_sale_price,
            unit_supply_price=unit_supply_price,
            shipping_fee_paid=shipping_fee_paid,
            shipping_fee_charged=shipping_fee_charged,
            platform_fee_rate=result.platform_fee_rate,
            platform_fee=result.platform_fee,
            ad_cost=ad_cost,
            return_cost=return_cost,
            gross_revenue=result.gross_revenue,
            supply_cost=result.supply_cost,
            net_shipping_cost=result.net_shipping_cost,
            gross_profit=result.gross_profit,
            vat_payable=result.vat_payable,
            net_profit=result.net_profit,
            margin_rate=result.margin_rate,
            status=status,
            ordered_at=ordered_at or datetime.utcnow(),
            memo=memo,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return {"status": "ok", "order_id": order.id, "net_profit": result.net_profit}


def list_orders(
    platform: str = "",
    status: str = "",
    year: int | None = None,
    month: int | None = None,
    limit: int = 200,
) -> dict:
    """주문 목록 조회."""
    with get_db() as db:
        q = db.query(Order)
        if platform:
            q = q.filter(Order.platform == platform)
        if status:
            q = q.filter(Order.status == status)
        if year:
            q = q.filter(
                Order.ordered_at >= datetime(year, 1, 1),
                Order.ordered_at < datetime(year + 1, 1, 1),
            )
        if month and year:
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            q = q.filter(
                Order.ordered_at >= datetime(year, month, 1),
                Order.ordered_at <= datetime(year, month, last_day, 23, 59, 59),
            )
        total = q.count()
        items = q.order_by(Order.ordered_at.desc()).limit(limit).all()
        return {
            "total": total,
            "items": [_order_to_dict(o) for o in items],
        }


def delete_order(order_id: int) -> bool:
    with get_db() as db:
        o = db.query(Order).filter_by(id=order_id).first()
        if not o:
            return False
        db.delete(o)
        db.commit()
    return True


def get_settlement_dashboard(year: int | None = None, month: int | None = None) -> dict:
    """정산 대시보드 데이터를 반환한다.

    Returns:
        {
          "summary": {gross_revenue, net_profit, order_count, margin_rate, vat_payable},
          "by_platform": {"coupang": {...}, "smartstore": {...}},
          "monthly": [{month, gross_revenue, net_profit, order_count}],
          "recent_orders": [...],
          "tax_estimate": {...},
        }
    """
    from app.settlement.calculator import aggregate_orders
    from app.settlement.tax_engine import calculate_tax, format_krw

    now = datetime.utcnow()
    target_year = year or now.year
    target_month = month or now.month

    with get_db() as db:
        # 이번 달 주문
        import calendar as _cal
        last_day = _cal.monthrange(target_year, target_month)[1]
        month_start = datetime(target_year, target_month, 1)
        month_end = datetime(target_year, target_month, last_day, 23, 59, 59)

        month_orders = db.query(Order).filter(
            Order.ordered_at >= month_start,
            Order.ordered_at <= month_end,
            Order.status.notin_(["cancelled", "returned"]),
        ).all()

        # 연간 주문
        year_start = datetime(target_year, 1, 1)
        year_end = datetime(target_year, 12, 31, 23, 59, 59)
        year_orders = db.query(Order).filter(
            Order.ordered_at >= year_start,
            Order.ordered_at <= year_end,
            Order.status.notin_(["cancelled", "returned"]),
        ).all()

        # 최근 20건
        recent = db.query(Order).order_by(Order.ordered_at.desc()).limit(20).all()

    def _sum(orders, field):
        return sum(getattr(o, field, 0) or 0 for o in orders)

    # 이번 달 요약
    m_revenue = _sum(month_orders, "gross_revenue")
    m_profit = _sum(month_orders, "net_profit")
    m_vat = _sum(month_orders, "vat_payable")
    m_count = len(month_orders)

    # 플랫폼별
    by_platform = {}
    for plat in ["coupang", "smartstore"]:
        po = [o for o in month_orders if o.platform == plat]
        by_platform[plat] = {
            "order_count": len(po),
            "gross_revenue": _sum(po, "gross_revenue"),
            "net_profit": _sum(po, "net_profit"),
            "platform_fee": _sum(po, "platform_fee"),
            "vat_payable": _sum(po, "vat_payable"),
        }

    # 월별 (연간)
    monthly = []
    for mo in range(1, 13):
        import calendar as _cal2
        ld = _cal2.monthrange(target_year, mo)[1]
        ms = datetime(target_year, mo, 1)
        me = datetime(target_year, mo, ld, 23, 59, 59)
        mo_orders = [o for o in year_orders if ms <= o.ordered_at <= me]
        monthly.append({
            "month": mo,
            "label": f"{mo}월",
            "gross_revenue": _sum(mo_orders, "gross_revenue"),
            "net_profit": _sum(mo_orders, "net_profit"),
            "order_count": len(mo_orders),
        })

    # 세금 추정 (연간 기준)
    y_revenue = _sum(year_orders, "gross_revenue")
    y_supply = _sum(year_orders, "supply_cost")
    y_fee = _sum(year_orders, "platform_fee")
    y_ship = _sum(year_orders, "net_shipping_cost")
    y_ad = _sum(year_orders, "ad_cost")
    tax_est = calculate_tax(
        gross_revenue=y_revenue,
        supply_cost=y_supply,
        platform_fee=y_fee,
        shipping_cost=y_ship,
        ad_cost=y_ad,
        year=target_year,
        quarter=0,
    )

    return {
        "year": target_year,
        "month": target_month,
        "summary": {
            "order_count": m_count,
            "gross_revenue": m_revenue,
            "net_profit": m_profit,
            "vat_payable": m_vat,
            "margin_rate": m_profit / m_revenue if m_revenue > 0 else 0,
        },
        "by_platform": by_platform,
        "monthly": monthly,
        "recent_orders": [_order_to_dict(o) for o in recent],
        "tax_estimate": {
            "year": target_year,
            "gross_revenue": tax_est.gross_revenue,
            "taxable_income": tax_est.taxable_income,
            "vat_payable": tax_est.vat_payable,
            "income_tax": tax_est.income_tax,
            "local_tax": tax_est.local_tax,
            "total_tax": tax_est.total_tax,
            "effective_rate": tax_est.effective_rate,
        },
    }


def get_profit_calculator_preview(
    platform: str,
    unit_sale_price: float,
    unit_supply_price: float,
    quantity: int = 1,
    shipping_fee_paid: float = 3000,
    shipping_fee_charged: float = 0,
    ad_cost: float = 0,
    return_cost: float = 0,
) -> dict:
    """실시간 순이익 미리보기 (DB 저장 없음)."""
    from app.settlement.calculator import calculate_order_profit
    r = calculate_order_profit(
        platform=platform,
        unit_sale_price=unit_sale_price,
        unit_supply_price=unit_supply_price,
        quantity=quantity,
        shipping_fee_paid=shipping_fee_paid,
        shipping_fee_charged=shipping_fee_charged,
        ad_cost=ad_cost,
        return_cost=return_cost,
    )
    return {
        "gross_revenue": r.gross_revenue,
        "supply_cost": r.supply_cost,
        "platform_fee": r.platform_fee,
        "platform_fee_rate": r.platform_fee_rate,
        "net_shipping_cost": r.net_shipping_cost,
        "ad_cost": r.ad_cost,
        "return_cost": r.return_cost,
        "gross_profit": r.gross_profit,
        "vat_payable": r.vat_payable,
        "net_profit": r.net_profit,
        "margin_rate": r.margin_rate,
    }


def _order_to_dict(o: Order) -> dict:
    return {
        "id": o.id,
        "product_id": o.product_id,
        "platform": o.platform,
        "platform_order_id": o.platform_order_id,
        "quantity": o.quantity,
        "unit_sale_price": float(o.unit_sale_price or 0),
        "unit_supply_price": float(o.unit_supply_price or 0),
        "gross_revenue": float(o.gross_revenue or 0),
        "supply_cost": float(o.supply_cost or 0),
        "platform_fee": float(o.platform_fee or 0),
        "platform_fee_rate": float(o.platform_fee_rate or 0),
        "net_shipping_cost": float(o.net_shipping_cost or 0),
        "ad_cost": float(o.ad_cost or 0),
        "return_cost": float(o.return_cost or 0),
        "vat_payable": float(o.vat_payable or 0),
        "net_profit": float(o.net_profit or 0),
        "margin_rate": float(o.margin_rate or 0),
        "status": o.status,
        "ordered_at": o.ordered_at.strftime("%Y-%m-%d %H:%M") if o.ordered_at else "",
        "memo": o.memo or "",
    }


# ── 재고·발주 자동화 (Inventory & MOQ Engine) ────────────────────────────────


def get_or_create_inventory(product_id: int, db) -> Inventory:
    """product_id에 해당하는 Inventory 레코드를 반환하거나 신규 생성한다."""
    inv = db.query(Inventory).filter_by(product_id=product_id).first()
    if not inv:
        prod = db.query(Product).filter_by(id=product_id).first()
        unit_cost = float(prod.supply_price) if prod else 0.0
        inv = Inventory(product_id=product_id, unit_cost=unit_cost)
        db.add(inv)
        db.flush()
    return inv


def get_inventory_dashboard() -> dict:
    """전체 재고 현황 + MOQ 발주 추천 목록을 반환한다."""
    from app.inventory.moq_engine import build_suggestions, StockStatus

    with get_db() as db:
        inventories = db.query(Inventory).all()
        products = db.query(Product).all()
        orders = db.query(Order).filter(
            Order.ordered_at >= datetime.utcnow() - timedelta(days=60)
        ).all()

        total_value = sum(inv.qty_on_hand * inv.unit_cost for inv in inventories)
        suggestions = build_suggestions(inventories, products, orders)

        critical = sum(1 for inv in inventories
                       if (inv.qty_on_hand - inv.qty_reserved) <= inv.safety_stock)
        warning = sum(1 for inv in inventories
                      if inv.safety_stock < (inv.qty_on_hand - inv.qty_reserved) <= inv.reorder_point)
        ok_count = len(inventories) - critical - warning

        return {
            "total_products": len(inventories),
            "critical": critical,
            "warning": warning,
            "ok": ok_count,
            "total_value": total_value,
            "suggestions": [
                {
                    "product_id": s.product_id,
                    "product_name": s.product_name,
                    "sku": s.sku,
                    "supplier": s.supplier,
                    "qty_on_hand": s.qty_on_hand,
                    "qty_reserved": s.qty_reserved,
                    "qty_incoming": s.qty_incoming,
                    "available_qty": s.available_qty,
                    "safety_stock": s.safety_stock,
                    "reorder_point": s.reorder_point,
                    "moq": s.moq,
                    "reorder_qty": s.reorder_qty,
                    "lead_time_days": s.lead_time_days,
                    "unit_cost": s.unit_cost,
                    "avg_daily_sales": s.avg_daily_sales,
                    "days_of_stock": s.days_of_stock,
                    "urgency": s.urgency,
                    "suggested_qty": s.suggested_qty,
                    "suggested_cost": s.suggested_cost,
                    "reason": s.reason,
                }
                for s in suggestions
            ],
            "all_inventories": [_inventory_to_dict(inv, products) for inv in inventories],
        }


def update_inventory(
    product_id: int,
    qty_delta: int,
    movement_type: str = "in_adjust",
    reference_id: int | None = None,
    reference_type: str = "manual",
    memo: str = "",
    safety_stock: int | None = None,
    reorder_point: int | None = None,
    moq: int | None = None,
    reorder_qty: int | None = None,
    lead_time_days: int | None = None,
    unit_cost: float | None = None,
    location: str | None = None,
) -> dict:
    """재고를 변경하고 StockMovement 이력을 기록한다.

    qty_delta > 0 이면 입고, < 0 이면 출고.
    설정값(safety_stock 등) 만 갱신할 경우 qty_delta=0으로 호출.
    """
    with get_db() as db:
        inv = get_or_create_inventory(product_id, db)

        # 설정값 갱신
        if safety_stock is not None:
            inv.safety_stock = safety_stock
        if reorder_point is not None:
            inv.reorder_point = reorder_point
        if moq is not None:
            inv.moq = moq
        if reorder_qty is not None:
            inv.reorder_qty = reorder_qty
        if lead_time_days is not None:
            inv.lead_time_days = lead_time_days
        if unit_cost is not None:
            inv.unit_cost = unit_cost
        if location is not None:
            inv.location = location

        if qty_delta != 0:
            inv.qty_on_hand += qty_delta
            if inv.qty_on_hand < 0:
                inv.qty_on_hand = 0

            mv = StockMovement(
                product_id=product_id,
                movement_type=movement_type,
                quantity=qty_delta,
                qty_after=inv.qty_on_hand,
                reference_id=reference_id,
                reference_type=reference_type,
                memo=memo,
            )
            db.add(mv)

        db.commit()
        return {"status": "ok", "qty_on_hand": inv.qty_on_hand}


def get_reorder_suggestions() -> list[dict]:
    """재발주 필요 상품 목록 (urgency=critical/warning 만 반환)."""
    return get_inventory_dashboard()["suggestions"]


def bulk_init_inventory(product_ids: list[int] | None = None) -> dict:
    """상품 목록에 대해 재고 레코드가 없으면 기본값으로 생성한다.

    product_ids=None 이면 전체 상품을 대상으로 한다.
    Returns:
        {"created": int, "already_exists": int, "product_ids": list[int]}
    """
    with get_db() as db:
        if product_ids is None:
            products = db.query(Product).all()
        else:
            products = db.query(Product).filter(Product.id.in_(product_ids)).all()

        created = 0
        already = 0
        created_ids = []
        for p in products:
            existing = db.query(Inventory).filter_by(product_id=p.id).first()
            if existing:
                already += 1
            else:
                inv = Inventory(
                    product_id=p.id,
                    qty_on_hand=0,
                    qty_reserved=0,
                    qty_incoming=0,
                    safety_stock=10,
                    reorder_point=20,
                    moq=1,
                    reorder_qty=50,
                    lead_time_days=7,
                    unit_cost=float(p.supply_price),
                    location="",
                )
                db.add(inv)
                created += 1
                created_ids.append(p.id)
        db.commit()
    return {"created": created, "already_exists": already, "product_ids": created_ids}


def get_recent_stock_movements(limit: int = 30) -> list[dict]:
    """전체 상품의 최근 재고 이동 이력을 반환한다."""
    with get_db() as db:
        rows = (
            db.query(StockMovement)
            .order_by(StockMovement.id.desc())
            .limit(limit)
            .all()
        )
        products = {p.id: p for p in db.query(Product).all()}
        return [
            {
                "id": r.id,
                "product_id": r.product_id,
                "product_name": (products[r.product_id].name[:35] if r.product_id in products else ""),
                "movement_type": r.movement_type,
                "quantity": r.quantity,
                "qty_after": r.qty_after,
                "memo": r.memo or "",
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            }
            for r in rows
        ]


def test_service_connection(service: str) -> dict:
    """서비스 연결을 실시간으로 테스트하고 결과를 반환한다."""
    import time
    start = time.monotonic()

    def _elapsed():
        return int((time.monotonic() - start) * 1000)

    try:
        if service == "telegram":
            from app.config import get_settings
            s = get_settings()
            if not s.telegram_bot_token:
                return {"ok": False, "service": service, "error": "BOT_TOKEN 미설정", "ms": _elapsed()}
            import requests
            r = requests.get(
                f"https://api.telegram.org/bot{s.telegram_bot_token}/getMe",
                timeout=8,
            )
            data = r.json()
            if not data.get("ok"):
                return {"ok": False, "service": service, "error": data.get("description", "Bot 오류"), "ms": _elapsed()}
            return {"ok": True, "service": service,
                    "detail": f'@{data["result"].get("username", "?")}', "ms": _elapsed()}

        elif service == "coupang":
            from app.config import get_settings
            s = get_settings()
            ak = s.coupang_access_key.strip()
            sk = s.coupang_secret_key.strip()
            vid = s.coupang_vendor_id.strip()
            if not (ak and sk and vid):
                return {"ok": False, "service": service, "error": "API 자격증명 미설정", "ms": _elapsed()}
            # 실제 API 호출로 HMAC 검증
            from app.platforms.coupang import reset_coupang_uploader, get_coupang_uploader
            reset_coupang_uploader()
            uploader = get_coupang_uploader()
            try:
                # 조회 전용 엔드포인트 — IP 화이트리스트 불필요
                r = uploader._get(
                    f"/v2/providers/openapi/apis/api/v4/vendors/{vid}"
                    f"/ordersheets?createdAtFrom=2099-01-01T00:00:00&createdAtTo=2099-01-01T01:00:00"
                    f"&status=ACCEPT&perPage=1"
                )
                if r.status_code == 200:
                    return {"ok": True, "service": service,
                            "detail": f"HMAC OK · Vendor: {vid}", "ms": _elapsed()}
                elif r.status_code == 403:
                    return {"ok": False, "service": service,
                            "error": f"IP 미화이트리스트 (HTTP 403) — openapisupport@coupang.com 등록 필요",
                            "ms": _elapsed()}
                else:
                    err = r.json().get("message", r.text[:100]) if r.headers.get("content-type","").startswith("application/json") else r.text[:100]
                    return {"ok": False, "service": service,
                            "error": f"HTTP {r.status_code}: {err}", "ms": _elapsed()}
            except Exception as exc:
                return {"ok": False, "service": service, "error": str(exc)[:150], "ms": _elapsed()}

        elif service == "smartstore":
            from app.config import get_settings
            s = get_settings()
            if not (s.naver_client_id and s.naver_client_secret):
                return {"ok": False, "service": service, "error": "Client ID/Secret 미설정", "ms": _elapsed()}
            from app.platforms.smartstore import SmartStoreUploader
            uploader = SmartStoreUploader()
            uploader._ensure_token()
            return {"ok": True, "service": service,
                    "detail": f"Token OK · Client: {s.naver_client_id[:10]}...", "ms": _elapsed()}

        elif service == "naver_search":
            from app.config import get_settings
            s = get_settings()
            if not (s.naver_search_client_id and s.naver_search_client_secret):
                return {"ok": False, "service": service, "error": "Search API 키 미설정", "ms": _elapsed()}
            import httpx
            r = httpx.get(
                "https://openapi.naver.com/v1/search/shop.json",
                params={"query": "테스트", "display": 1},
                headers={
                    "X-Naver-Client-Id": s.naver_search_client_id,
                    "X-Naver-Client-Secret": s.naver_search_client_secret,
                },
                timeout=8,
            )
            if r.status_code == 200:
                return {"ok": True, "service": service, "detail": "API 응답 정상", "ms": _elapsed()}
            return {"ok": False, "service": service, "error": f"HTTP {r.status_code}", "ms": _elapsed()}

        elif service == "claude":
            from app.config import get_settings
            s = get_settings()
            if not s.claude_api_key:
                return {"ok": False, "service": service, "error": "API 키 미설정", "ms": _elapsed()}
            import anthropic
            client = anthropic.Anthropic(api_key=s.claude_api_key)
            msg = client.messages.create(
                model=s.claude_model,
                max_tokens=10,
                messages=[{"role": "user", "content": "hi"}],
            )
            return {"ok": True, "service": service,
                    "detail": f"모델: {s.claude_model}", "ms": _elapsed()}

        elif service == "database":
            with get_db() as db:
                cnt = db.query(Product).count()
            return {"ok": True, "service": service,
                    "detail": f"상품 {cnt}개 등록됨", "ms": _elapsed()}

        else:
            return {"ok": False, "service": service, "error": f"알 수 없는 서비스: {service}", "ms": _elapsed()}

    except Exception as exc:
        return {"ok": False, "service": service, "error": str(exc)[:100], "ms": _elapsed()}


# ── 발주서 관리 ────────────────────────────────────────────────────────────────

def _next_po_number() -> str:
    """PO-YYYYMMDD-NNN 형태의 발주 번호 자동 생성."""
    today = datetime.utcnow().strftime("%Y%m%d")
    with get_db() as db:
        count = db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number.like(f"PO-{today}-%")
        ).count()
    return f"PO-{today}-{count + 1:03d}"


def create_purchase_order(
    items: list[dict],
    supplier: str = "",
    memo: str = "",
    expected_days: int = 7,
) -> dict:
    """발주서를 생성하고 inventory.qty_incoming을 업데이트한다.

    items: [{"product_id": int, "quantity": int, "unit_cost": float}]
    """
    if not items:
        return {"status": "error", "error": "발주 항목이 없습니다"}

    po_number = _next_po_number()
    expected_at = datetime.utcnow() + timedelta(days=expected_days)

    with get_db() as db:
        total = 0.0
        po_items = []

        for item in items:
            prod = db.query(Product).filter_by(id=item["product_id"]).first()
            if not prod:
                continue
            qty = int(item["quantity"])
            cost = float(item.get("unit_cost") or prod.supply_price)
            line_total = qty * cost
            total += line_total

            po_items.append(PurchaseOrderItem(
                product_id=item["product_id"],
                quantity=qty,
                unit_cost=cost,
                total_cost=line_total,
            ))

            # 입고 예정 수량 증가
            inv = get_or_create_inventory(item["product_id"], db)
            inv.qty_incoming += qty

        po = PurchaseOrder(
            po_number=po_number,
            supplier=supplier,
            status="confirmed",
            total_amount=total,
            memo=memo,
            ordered_at=datetime.utcnow(),
            expected_at=expected_at,
        )
        db.add(po)
        db.flush()

        for poi in po_items:
            poi.po_id = po.id
            db.add(poi)

        db.commit()
        _notify_po_created(po_number, supplier, len(po_items), total)
        return {"status": "ok", "po_id": po.id, "po_number": po_number, "total_amount": total}


def list_purchase_orders(status: str = "", limit: int = 100) -> list[dict]:
    """발주서 목록 조회."""
    with get_db() as db:
        q = db.query(PurchaseOrder)
        if status:
            q = q.filter(PurchaseOrder.status == status)
        orders = q.order_by(PurchaseOrder.created_at.desc()).limit(limit).all()

        result = []
        for po in orders:
            items = db.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
            prods = {p.id: p for p in db.query(Product).filter(
                Product.id.in_([i.product_id for i in items])
            ).all()}
            result.append({
                "id": po.id,
                "po_number": po.po_number,
                "supplier": po.supplier,
                "status": po.status,
                "total_amount": po.total_amount,
                "memo": po.memo,
                "ordered_at": po.ordered_at.strftime("%Y-%m-%d") if po.ordered_at else "",
                "expected_at": po.expected_at.strftime("%Y-%m-%d") if po.expected_at else "",
                "received_at": po.received_at.strftime("%Y-%m-%d") if po.received_at else "",
                "created_at": po.created_at.strftime("%Y-%m-%d %H:%M") if po.created_at else "",
                "items": [
                    {
                        "product_id": i.product_id,
                        "product_name": prods[i.product_id].name if i.product_id in prods else "",
                        "sku": prods[i.product_id].sku if i.product_id in prods else "",
                        "quantity": i.quantity,
                        "unit_cost": i.unit_cost,
                        "total_cost": i.total_cost,
                        "qty_received": i.qty_received,
                    }
                    for i in items
                ],
            })
        return result


def receive_purchase_order(po_id: int, received_items: list[dict] | None = None) -> dict:
    """발주서 입고 처리 — 재고에 반영하고 status를 received로 변경.

    received_items: [{"product_id": int, "qty_received": int}]
    None 이면 발주 수량 전체 입고 처리.
    """
    with get_db() as db:
        po = db.query(PurchaseOrder).filter_by(id=po_id).first()
        if not po:
            return {"status": "error", "error": "발주서 없음"}
        if po.status == "received":
            return {"status": "error", "error": "이미 입고 완료된 발주서"}

        items = db.query(PurchaseOrderItem).filter_by(po_id=po_id).all()
        recv_map = {}
        if received_items:
            recv_map = {r["product_id"]: r["qty_received"] for r in received_items}

        for item in items:
            qty = recv_map.get(item.product_id, item.quantity)
            item.qty_received = qty

            inv = get_or_create_inventory(item.product_id, db)
            inv.qty_on_hand += qty
            inv.qty_incoming = max(0, inv.qty_incoming - item.quantity)

            mv = StockMovement(
                product_id=item.product_id,
                movement_type="in_purchase",
                quantity=qty,
                qty_after=inv.qty_on_hand,
                reference_id=po_id,
                reference_type="po",
                memo=f"발주 입고 {po.po_number}",
            )
            db.add(mv)

        po.status = "received"
        po.received_at = datetime.utcnow()
        db.commit()
        _notify_po_received(po.po_number, len(items))
        return {"status": "ok", "po_id": po_id}


def update_po_status(po_id: int, status: str) -> dict:
    """발주서 상태만 변경한다 (cancel 등)."""
    with get_db() as db:
        po = db.query(PurchaseOrder).filter_by(id=po_id).first()
        if not po:
            return {"status": "error", "error": "발주서 없음"}
        if status == "cancelled" and po.status not in ("draft", "confirmed"):
            return {"status": "error", "error": "취소 불가 상태"}

        if status == "cancelled":
            items = db.query(PurchaseOrderItem).filter_by(po_id=po_id).all()
            for item in items:
                inv = db.query(Inventory).filter_by(product_id=item.product_id).first()
                if inv:
                    inv.qty_incoming = max(0, inv.qty_incoming - item.quantity)

        po.status = status
        db.commit()
        return {"status": "ok"}


def get_stock_movements(product_id: int, limit: int = 50) -> list[dict]:
    """특정 상품의 재고 이동 이력을 반환한다."""
    with get_db() as db:
        rows = (
            db.query(StockMovement)
            .filter_by(product_id=product_id)
            .order_by(StockMovement.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "movement_type": r.movement_type,
                "quantity": r.quantity,
                "qty_after": r.qty_after,
                "reference_id": r.reference_id,
                "reference_type": r.reference_type,
                "memo": r.memo,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            }
            for r in rows
        ]


# ── 내부 헬퍼 ──────────────────────────────────────────────────────────────────

# ── 알림 엔진 (Notification Engine) ──────────────────────────────────────────

def test_telegram_connection() -> dict:
    """텔레그램 연결 테스트 — 봇 인증 + 테스트 메시지 발송."""
    from app.notify.telegram import get_bot
    return get_bot().test_connection()


def send_daily_report() -> dict:
    """이번 달 정산 현황을 텔레그램으로 발송한다."""
    from app.notify.events import notify, NotifyLevel, EventType, build_daily_report
    dashboard = get_settlement_dashboard()
    body = build_daily_report(dashboard)
    ok = notify(
        level=NotifyLevel.INFO,
        title="📊 일일 정산 리포트",
        body=body,
        event_type=EventType.DAILY_REPORT,
    )
    return {"status": "ok" if ok else "failed"}


def trigger_inventory_alerts() -> dict:
    """재고 위험·경고 상품을 스캔하고 텔레그램으로 일괄 알림 발송."""
    from app.notify.events import (
        notify, NotifyLevel, EventType,
        build_inventory_critical, build_inventory_warning,
    )
    suggestions = get_reorder_suggestions()
    critical = [s for s in suggestions if s["urgency"] == "critical"]
    warning  = [s for s in suggestions if s["urgency"] == "warning"]

    sent = 0
    if critical:
        ok = notify(
            level=NotifyLevel.CRITICAL,
            title=f"재고 위험 {len(critical)}개 — 즉시 발주 필요",
            body=build_inventory_critical(critical),
            event_type=EventType.INVENTORY_CRITICAL,
        )
        if ok:
            sent += 1

    if warning:
        ok = notify(
            level=NotifyLevel.WARNING,
            title=f"발주 권장 {len(warning)}개",
            body=build_inventory_warning(warning),
            event_type=EventType.INVENTORY_WARNING,
        )
        if ok:
            sent += 1

    return {"status": "ok", "critical": len(critical), "warning": len(warning), "sent": sent}


def notify_pipeline_done(
    collected: int, passed: int, imported: int, ok: int, fail: int
) -> None:
    """파이프라인 완료 알림 (성공 건이 있을 때만 발송)."""
    if ok == 0 and imported == 0:
        return
    from app.notify.events import notify, NotifyLevel, EventType, build_pipeline_done
    notify(
        level=NotifyLevel.SUCCESS if fail == 0 else NotifyLevel.WARNING,
        title=f"파이프라인 완료 — 업로드 {ok}건" + (f" (실패 {fail}건)" if fail else ""),
        body=build_pipeline_done(collected, passed, imported, ok, fail),
        event_type=EventType.PIPELINE_DONE,
    )


def get_notification_logs(limit: int = 50, level: str = "") -> list[dict]:
    """알림 발송 이력 조회."""
    with get_db() as db:
        q = db.query(NotificationLog)
        if level:
            q = q.filter(NotificationLog.level == level)
        rows = q.order_by(NotificationLog.sent_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "level": r.level,
                "title": r.title,
                "body": r.body,
                "status": r.status,
                "error": r.error,
                "sent_at": r.sent_at.strftime("%Y-%m-%d %H:%M") if r.sent_at else "",
            }
            for r in rows
        ]


# ── 시스템 하드닝 (Health · Circuit Breaker) ─────────────────────────────────

def run_health_check(save_logs: bool = True) -> dict:
    """전체 서비스 헬스 체크 실행 후 결과를 반환한다."""
    from app.hardening.health import run_all_checks
    return run_all_checks(save_logs=save_logs)


def get_circuit_breaker_status() -> list[dict]:
    """모든 Circuit Breaker 상태 목록을 반환한다."""
    from app.hardening.circuit_breaker import all_breakers
    return all_breakers()


def reset_circuit_breaker(service: str) -> dict:
    """지정 서비스의 Circuit Breaker를 수동 리셋한다."""
    from app.hardening.circuit_breaker import get_circuit_breaker
    try:
        get_circuit_breaker(service).reset()
        return {"status": "ok", "service": service}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def get_health_logs(service: str = "", limit: int = 100) -> list[dict]:
    """헬스 체크 이력 조회 (최근 N건)."""
    with get_db() as db:
        q = db.query(HealthCheckLog)
        if service:
            q = q.filter(HealthCheckLog.service == service)
        rows = q.order_by(HealthCheckLog.checked_at.desc()).limit(limit).all()
        return [
            {
                "id":         r.id,
                "service":    r.service,
                "status":     r.status,
                "latency_ms": r.latency_ms,
                "detail":     r.detail,
                "error":      r.error,
                "checked_at": r.checked_at.strftime("%Y-%m-%d %H:%M:%S") if r.checked_at else "",
            }
            for r in rows
        ]


def get_rate_limiter_status() -> list[dict]:
    """모든 Rate Limiter 현재 상태를 반환한다."""
    from app.hardening.rate_limiter import all_limiters
    return all_limiters()


def get_dashboard_overview() -> dict:
    """대시보드 — 전체 현황을 한 번에 로드한다.

    반환 구조:
      products, settlement, inventory_summary,
      recent_notifications, scheduler, recent_orders,
      upload_stats, monthly_trend
    """
    # ── 상품·업로드 ─────────────────────────────────────────────────
    prod_stats = get_stats()

    # ── 정산 (이번 달) ────────────────────────────────────────────────
    try:
        settle = get_settlement_dashboard()
    except Exception:
        settle = {
            "summary": {"order_count": 0, "gross_revenue": 0,
                        "net_profit": 0, "vat_payable": 0, "margin_rate": 0},
            "by_platform": {"coupang": {}, "smartstore": {}},
            "monthly": [{"month": m, "label": f"{m}월",
                         "gross_revenue": 0, "net_profit": 0,
                         "order_count": 0} for m in range(1, 13)],
            "recent_orders": [],
            "tax_estimate": {},
        }

    # ── 재고 요약 ─────────────────────────────────────────────────────
    try:
        inv = get_inventory_dashboard()
        inv_summary = {
            "total": inv["total_products"],
            "critical": inv["critical"],
            "warning": inv["warning"],
            "ok": inv["ok"],
            "total_value": inv["total_value"],
            "top_alerts": inv["suggestions"][:5],
        }
    except Exception:
        inv_summary = {"total": 0, "critical": 0, "warning": 0,
                       "ok": 0, "total_value": 0, "top_alerts": []}

    # ── 최근 알림 5건 ─────────────────────────────────────────────────
    try:
        recent_notifs = get_notification_logs(limit=5)
    except Exception:
        recent_notifs = []

    # ── 스케줄러 ─────────────────────────────────────────────────────
    try:
        sched = get_scheduler_status()
    except Exception:
        sched = {"running": False, "enabled_jobs": 0,
                 "total_jobs": 0, "jobs": [], "timezone": "Asia/Seoul"}

    # ── 최근 주문 10건 ────────────────────────────────────────────────
    try:
        recent_orders = list_orders(limit=10)["items"]
    except Exception:
        recent_orders = []

    # ── 업로드 실패 수 ────────────────────────────────────────────────
    with get_db() as db:
        upload_fail = db.query(Listing).filter_by(status="failed").count()
        upload_ok   = db.query(Listing).filter_by(status="success").count()

    # ── 연간 월별 트렌드 데이터 (차트용) ─────────────────────────────
    monthly_trend = settle.get("monthly", [])

    return {
        "products": prod_stats,
        "settlement": settle["summary"],
        "by_platform": settle["by_platform"],
        "monthly_trend": monthly_trend,
        "inventory": inv_summary,
        "recent_notifications": recent_notifs,
        "scheduler": sched,
        "recent_orders": recent_orders,
        "upload_ok": upload_ok,
        "upload_fail": upload_fail,
        "tax_estimate": settle.get("tax_estimate", {}),
    }


def get_notification_stats() -> dict:
    """알림 통계 (최근 7일 기준)."""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=7)
    with get_db() as db:
        total = db.query(NotificationLog).filter(NotificationLog.sent_at >= cutoff).count()
        ok_cnt = db.query(NotificationLog).filter(
            NotificationLog.sent_at >= cutoff, NotificationLog.status == "ok"
        ).count()
        fail_cnt = total - ok_cnt
        by_level = {}
        for lv in ("critical", "warning", "info", "success"):
            by_level[lv] = db.query(NotificationLog).filter(
                NotificationLog.sent_at >= cutoff, NotificationLog.level == lv
            ).count()
    return {
        "total_7d": total,
        "ok_7d": ok_cnt,
        "failed_7d": fail_cnt,
        "by_level": by_level,
    }


# ── 내부 알림 헬퍼 ─────────────────────────────────────────────────────────────

def _notify_upload_success(platform: str, product_name: str, platform_id: str) -> None:
    try:
        from app.notify.events import notify, NotifyLevel, EventType, build_upload_success
        notify(
            level=NotifyLevel.SUCCESS,
            title="상품 업로드 성공",
            body=build_upload_success(platform, product_name, platform_id),
            event_type=EventType.UPLOAD_SUCCESS,
        )
    except Exception:
        pass


def _notify_upload_failed(platform: str, product_name: str, error: str) -> None:
    try:
        from app.notify.events import notify, NotifyLevel, EventType, build_upload_failed
        notify(
            level=NotifyLevel.WARNING,
            title="상품 업로드 실패",
            body=build_upload_failed(platform, product_name, error),
            event_type=EventType.UPLOAD_FAILED,
        )
    except Exception:
        pass


def _notify_po_created(po_number: str, supplier: str, item_count: int, total: float) -> None:
    try:
        from app.notify.events import notify, NotifyLevel, EventType, build_po_created
        notify(
            level=NotifyLevel.INFO,
            title="발주서 생성",
            body=build_po_created(po_number, supplier, item_count, total),
            event_type=EventType.PO_CREATED,
        )
    except Exception:
        pass


def _notify_po_received(po_number: str, item_count: int) -> None:
    try:
        from app.notify.events import notify, NotifyLevel, EventType, build_po_received
        notify(
            level=NotifyLevel.SUCCESS,
            title="입고 완료",
            body=build_po_received(po_number, item_count),
            event_type=EventType.PO_RECEIVED,
        )
    except Exception:
        pass


# ── 스케줄러 제어 (Scheduler & Automation) ───────────────────────────────────

def get_scheduler_status() -> dict:
    """스케줄러 전체 상태 + 작업 목록을 반환한다."""
    from app.scheduler.manager import get_scheduler
    return get_scheduler().get_status()


def toggle_scheduled_job(job_id: str, enabled: bool) -> dict:
    """작업 활성/비활성 전환."""
    from app.scheduler.manager import get_scheduler
    return get_scheduler().toggle(job_id, enabled)


def run_job_now(job_id: str) -> dict:
    """작업을 즉시 실행 (백그라운드 스레드)."""
    from app.scheduler.manager import get_scheduler
    return get_scheduler().run_now(job_id)


def update_job_cron(job_id: str, cron_expr: str) -> dict:
    """작업 cron 표현식 변경."""
    from app.scheduler.manager import get_scheduler
    return get_scheduler().update_cron(job_id, cron_expr)


def get_job_run_logs(job_id: str = "", limit: int = 50) -> list[dict]:
    """작업 실행 이력 조회."""
    with get_db() as db:
        q = db.query(JobRunLog)
        if job_id:
            q = q.filter(JobRunLog.job_id == job_id)
        rows = q.order_by(JobRunLog.started_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "job_id": r.job_id,
                "started_at": r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else "",
                "finished_at": r.finished_at.strftime("%Y-%m-%d %H:%M:%S") if r.finished_at else "",
                "duration_sec": (
                    round((r.finished_at - r.started_at).total_seconds(), 1)
                    if r.finished_at and r.started_at else None
                ),
                "status": r.status,
                "result": r.result,
                "error": r.error,
            }
            for r in rows
        ]


def _inventory_to_dict(inv: Inventory, products) -> dict:
    prod_map = {p.id: p for p in products} if not isinstance(products, dict) else products
    prod = prod_map.get(inv.product_id)
    available = inv.qty_on_hand - inv.qty_reserved

    if available <= inv.safety_stock:
        urgency = "critical"
    elif available <= inv.reorder_point:
        urgency = "warning"
    else:
        urgency = "ok"

    return {
        "id": inv.id,
        "product_id": inv.product_id,
        "product_name": prod.name if prod else "",
        "sku": prod.sku if prod else "",
        "source": prod.source if prod else "",
        "qty_on_hand": inv.qty_on_hand,
        "qty_reserved": inv.qty_reserved,
        "qty_incoming": inv.qty_incoming,
        "available_qty": available,
        "safety_stock": inv.safety_stock,
        "reorder_point": inv.reorder_point,
        "moq": inv.moq,
        "reorder_qty": inv.reorder_qty,
        "lead_time_days": inv.lead_time_days,
        "unit_cost": inv.unit_cost,
        "stock_value": inv.qty_on_hand * inv.unit_cost,
        "location": inv.location,
        "urgency": urgency,
        "updated_at": inv.updated_at.strftime("%Y-%m-%d %H:%M") if inv.updated_at else "",
    }


def _product_to_dict(p: Product, full: bool = False) -> dict:
    d = {
        "id": p.id,
        "sku": p.sku,
        "source": p.source,
        "name": p.name,
        "supply_price": float(p.supply_price),
        "sell_price": float(p.sell_price),
        "status": p.status,
        "category": p.category,
        "images": json.loads(p.images or "[]"),
    }
    if full:
        d.update({
            "source_url": p.source_url,
            "brand": p.brand,
            "origin": p.origin,
            "material": p.material,
            "detail_images": json.loads(p.detail_images or "[]"),
            "options": json.loads(p.options or "[]"),
            "detail_html": p.detail_html,
        })
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# ── 운영 자동화 (7단계: 주문수집 → 자동발주 → 송장등록 → 재고동기화) ──────────
# ═══════════════════════════════════════════════════════════════════════════════

def collect_platform_orders(hours_back: int = 3) -> dict:
    """쿠팡·스마트스토어에서 신규 주문을 수집해 platform_orders 테이블에 저장한다.

    Returns:
        {"coupang": {"collected": int, "new": int},
         "smartstore": {"collected": int, "new": int},
         "total_new": int}
    """
    result: dict = {"coupang": {"collected": 0, "new": 0},
                    "smartstore": {"collected": 0, "new": 0}, "total_new": 0}

    # ── 쿠팡 ──────────────────────────────────────────────────────────────────
    try:
        from app.platforms.coupang import get_coupang_uploader
        uploader = get_coupang_uploader()
        cp_orders = uploader.get_orders(status="ACCEPT", hours_back=hours_back)
        result["coupang"]["collected"] = len(cp_orders)

        with get_db() as db:
            for o in cp_orders:
                exists = db.query(PlatformOrder).filter_by(
                    platform="coupang",
                    platform_item_id=o["orderItemId"],
                ).first()
                if exists:
                    continue
                # 내부 product 매칭 (vendorItemId 기반 listing 조회)
                listing = db.query(Listing).filter_by(
                    platform="coupang",
                    platform_id=o["vendorItemId"],
                ).first()
                product_id = listing.product_id if listing else None

                po = PlatformOrder(
                    platform="coupang",
                    platform_order_id=o["orderId"],
                    platform_item_id=o["orderItemId"],
                    vendor_item_id=o["vendorItemId"],
                    product_id=product_id,
                    product_name=o["productName"],
                    quantity=o["quantity"],
                    unit_price=o["salesPrice"],
                    buyer_name=o["buyerName"],
                    receiver_name=o["receiverName"],
                    shipping_address=o["receiverAddr"],
                    receiver_phone=o["receiverPhone"],
                    shipping_message=o["shippingMessage"],
                    status="new",
                )
                db.add(po)
                result["coupang"]["new"] += 1
            db.commit()
    except Exception as exc:
        logger.error("쿠팡 주문 수집 실패: %s", exc)

    # ── 스마트스토어 ──────────────────────────────────────────────────────────
    try:
        from datetime import datetime, timedelta
        from app.platforms.smartstore import get_smartstore_uploader
        ss_uploader = get_smartstore_uploader()
        now = datetime.now()
        from_date = (now - timedelta(hours=hours_back)).strftime("%Y%m%d")
        to_date = now.strftime("%Y%m%d")
        ss_orders = ss_uploader.get_orders(from_date=from_date, to_date=to_date)
        result["smartstore"]["collected"] = len(ss_orders)

        with get_db() as db:
            for o in ss_orders:
                exists = db.query(PlatformOrder).filter_by(
                    platform="smartstore",
                    platform_item_id=o["productOrderId"],
                ).first()
                if exists:
                    continue
                listing = db.query(Listing).filter_by(
                    platform="smartstore",
                    platform_id=o["originProductNo"],
                ).first()
                product_id = listing.product_id if listing else None

                po = PlatformOrder(
                    platform="smartstore",
                    platform_order_id=o["orderId"],
                    platform_item_id=o["productOrderId"],
                    origin_product_no=o["originProductNo"],
                    product_id=product_id,
                    product_name=o["productName"],
                    quantity=o["quantity"],
                    unit_price=o["unitPrice"],
                    buyer_name=o["buyerName"],
                    receiver_name=o["receiverName"],
                    shipping_address=o["receiverAddr"],
                    receiver_phone=o["receiverPhone"],
                    shipping_message=o["shippingMessage"],
                    status="new",
                )
                db.add(po)
                result["smartstore"]["new"] += 1
            db.commit()
    except Exception as exc:
        logger.error("스마트스토어 주문 수집 실패: %s", exc)

    result["total_new"] = result["coupang"]["new"] + result["smartstore"]["new"]

    # 신규 주문 있으면 텔레그램 알림
    if result["total_new"] > 0:
        try:
            from app.notify.events import notify, NotifyLevel, EventType
            notify(
                level=NotifyLevel.INFO,
                title=f"신규 주문 {result['total_new']}건 수집",
                body=(f"쿠팡 {result['coupang']['new']}건 "
                      f"/ 스마트스토어 {result['smartstore']['new']}건"),
                event_type=EventType.ORDER_NEW,
            )
        except Exception:
            pass

    return result


def list_platform_orders(status: str = "", platform: str = "",
                         limit: int = 100) -> dict:
    """수집된 플랫폼 주문 목록 조회."""
    with get_db() as db:
        q = db.query(PlatformOrder)
        if status:
            q = q.filter(PlatformOrder.status == status)
        if platform:
            q = q.filter(PlatformOrder.platform == platform)
        total = q.count()
        rows = q.order_by(PlatformOrder.ordered_at.desc()).limit(limit).all()
        return {
            "total": total,
            "items": [_platform_order_to_dict(r) for r in rows],
        }


def register_invoice_to_platform(platform_order_id_internal: int,
                                  delivery_company: str,
                                  tracking_number: str) -> dict:
    """PlatformOrder ID로 해당 주문에 운송장을 등록하고 플랫폼에 발송처리한다."""
    with get_db() as db:
        po = db.query(PlatformOrder).filter_by(id=platform_order_id_internal).first()
        if not po:
            return {"ok": False, "error": "주문 없음"}

        if po.platform == "coupang":
            from app.platforms.coupang import get_coupang_uploader
            res = get_coupang_uploader().register_shipment(
                po.platform_order_id, po.platform_item_id,
                delivery_company, tracking_number,
            )
        elif po.platform == "smartstore":
            from app.platforms.smartstore import get_smartstore_uploader
            res = get_smartstore_uploader().dispatch_product_order(
                po.platform_item_id, delivery_company, tracking_number,
            )
        else:
            return {"ok": False, "error": f"알 수 없는 플랫폼: {po.platform}"}

        if res.get("ok"):
            po.delivery_company = delivery_company
            po.tracking_number = tracking_number
            po.invoice_registered = True
            po.status = "shipped"
            po.shipped_at = datetime.utcnow()
            db.commit()

        return res


def sync_platform_inventory() -> dict:
    """내부 재고 DB → 쿠팡·스마트스토어 재고 수량 일괄 동기화.

    Listing 테이블의 platform_id를 기반으로 각 플랫폼 재고를 업데이트.
    Returns: {"updated": int, "failed": int, "skipped": int}
    """
    updated = failed = skipped = 0

    with get_db() as db:
        inventories = db.query(Inventory).all()
        inv_map = {inv.product_id: inv for inv in inventories}

        listings = db.query(Listing).filter_by(status="success").all()

        from app.platforms.coupang import get_coupang_uploader
        from app.platforms.smartstore import get_smartstore_uploader
        cp = get_coupang_uploader()
        ss = get_smartstore_uploader()

        for listing in listings:
            inv = inv_map.get(listing.product_id)
            if not inv:
                skipped += 1
                continue

            available = max(0, inv.qty_on_hand - inv.qty_reserved)

            try:
                if listing.platform == "coupang":
                    res = cp.update_vendor_item_stock(listing.platform_id, available)
                elif listing.platform == "smartstore":
                    res = ss.update_stock(listing.platform_id, listing.platform_id, available)
                else:
                    skipped += 1
                    continue

                if res.get("ok"):
                    updated += 1
                else:
                    failed += 1
                    logger.warning("재고 동기화 실패 [%s/%s]: %s",
                                   listing.platform, listing.platform_id, res.get("error"))
            except Exception as exc:
                failed += 1
                logger.error("재고 동기화 예외 [%s/%s]: %s",
                             listing.platform, listing.platform_id, exc)

    return {"updated": updated, "failed": failed, "skipped": skipped}


def sync_prices_to_platforms(min_margin_pct: float | None = None) -> dict:
    """마진 계산 후 플랫폼 가격을 업데이트한다.

    목표 마진(기본 25%)을 기준으로 재계산된 판매가를 쿠팡·스마트스토어에 반영.
    Returns: {"updated": int, "failed": int, "skipped": int}
    """
    from app.config import get_settings
    s = get_settings()
    target_margin = min_margin_pct or getattr(s, "pricing_target_margin_pct", 0.25)
    fee_cp = getattr(s, "pricing_coupang_fee_pct", 0.107)
    fee_ss = getattr(s, "pricing_naver_fee_pct", 0.035)
    ship_cost = getattr(s, "pricing_shipping_cost", 2500.0)

    updated = failed = skipped = 0

    with get_db() as db:
        listings = db.query(Listing).filter_by(status="success").all()
        prod_ids = list({l.product_id for l in listings})
        products = db.query(Product).filter(Product.id.in_(prod_ids)).all()
        prod_map = {p.id: p for p in products}

        from app.platforms.coupang import get_coupang_uploader
        from app.platforms.smartstore import get_smartstore_uploader
        cp = get_coupang_uploader()
        ss = get_smartstore_uploader()

        for listing in listings:
            prod = prod_map.get(listing.product_id)
            if not prod:
                skipped += 1
                continue

            supply = float(prod.supply_price)
            if supply <= 0:
                skipped += 1
                continue

            fee = fee_cp if listing.platform == "coupang" else fee_ss
            new_price = int((supply + ship_cost) / (1 - fee - target_margin))
            current_price = int(prod.sell_price)

            # 5% 이상 차이날 때만 업데이트 (과도한 API 호출 방지)
            if abs(new_price - current_price) / max(current_price, 1) < 0.05:
                skipped += 1
                continue

            try:
                if listing.platform == "coupang":
                    res = cp.update_product_price(listing.platform_id, new_price)
                elif listing.platform == "smartstore":
                    res = ss.update_price(listing.platform_id, new_price)
                else:
                    skipped += 1
                    continue

                if res.get("ok"):
                    prod.sell_price = new_price
                    updated += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                logger.error("가격 동기화 예외 [%s]: %s", listing.platform_id, exc)

        if updated > 0:
            db.commit()

    return {"updated": updated, "failed": failed, "skipped": skipped}


# ── 대량 수집 + AI 선별 파이프라인 ───────────────────────────────────────────────

def bulk_collect_and_score(
    sources: list[str] | None = None,
    keywords: list[str] | None = None,
    limit_per_kw: int = 50,
    min_score: float = 80.0,
    min_margin_pct: float = 0.25,
    min_price: int = 3000,
    auto_import: bool = False,
    save_raw: bool = True,
) -> dict:
    """공급사 어댑터 레지스트리 → 대량 수집 → 중복제거 → 공급사별 AI 점수 → 선별.

    Args:
        sources: 공급사 ID 목록 (None = 전체 활성 어댑터)
        keywords: 검색 키워드 목록 (None = 최근 시장분석 키워드)
        limit_per_kw: 키워드당 수집 한도
        min_score: 최소 판매점수 (0~100), 기본 80
        min_margin_pct: 최소 마진율
        auto_import: True면 통과 상품 자동 import + 업로드
        save_raw: True면 원본을 supplier_raw_products 테이블에 저장
    Returns:
        {"collected": int, "deduped": int, "scored": int, "passed": int,
         "imported": int, "products": [scored_product_dict]}
    """
    from app.suppliers.registry import search_all, list_registered
    from app.ai_scoring import score_products

    # ── 1. 키워드 결정 ────────────────────────────────────────────────────────
    if not keywords:
        history = get_market_history(limit=5)
        keywords = [h["keyword"] for h in history] or ["인기상품", "생활용품", "주방용품"]

    # ── 2. 어댑터 레지스트리를 통한 대량 수집 ────────────────────────────────
    from app.suppliers.base import NormalizedProduct as NP
    raw_products: list[NP] = []

    for kw in keywords[:5]:
        items = search_all(
            keyword=kw,
            limit_per_supplier=limit_per_kw,
            min_price=min_price,
            moq=1,
            suppliers=sources,
        )
        raw_products.extend(items)
        logger.debug("키워드 '%s': %d개 수집", kw, len(items))

    collected = len(raw_products)

    # ── 3. 원본 DB 저장 (감사 이력) ───────────────────────────────────────────
    if save_raw and raw_products:
        _save_raw_products(raw_products)

    # ── 4. 중복 제거 (이름 기반 최저가 선택) ─────────────────────────────────
    deduped = _deduplicate_normalized(raw_products)

    # ── 5. 공급사별 AI 점수 계산 ──────────────────────────────────────────────
    passed_with_scores = score_products(
        deduped,
        min_score=min_score,
        target_margin=min_margin_pct,
        apply_claude=True,
        keywords=keywords,
    )

    # ── 6. 결과 직렬화 ────────────────────────────────────────────────────────
    sell_fee = 0.108
    ship = 3000.0
    result_products = []
    for prod, score_res in passed_with_scores:
        sell_price = int(prod.supply_price * 3.5)
        margin = (sell_price - prod.supply_price - ship - sell_price * sell_fee) / sell_price
        result_products.append({
            "supplier_id": prod.supplier_id,
            "source_id": prod.raw_id,
            "name": prod.name,
            "supply_price": prod.supply_price,
            "estimated_sell_price": sell_price,
            "estimated_margin": round(margin * 100, 1),
            "moq": prod.moq,
            "stock": prod.stock,
            "shipping_fee": prod.shipping_fee,
            "lead_time_days": prod.lead_time_days,
            "category": prod.category,
            "images": prod.images[:3],
            "score": score_res.total,
            "score_breakdown": score_res.breakdown,
        })

    # ── 7. 자동 import (선택) ──────────────────────────────────────────────────
    imported = 0
    if auto_import:
        for p in result_products[:20]:
            try:
                res = import_product(
                    source=p["supplier_id"],
                    source_id=p["source_id"],
                    sell_price=p["estimated_sell_price"],
                    ai_enhance=True,
                )
                if res["status"] in ("imported", "updated"):
                    upload_product(res["id"], ["coupang", "smartstore"])
                    imported += 1
            except Exception as exc:
                logger.warning("자동 import 실패 [%s]: %s", p["source_id"], exc)

    return {
        "collected": collected,
        "deduped": len(deduped),
        "scored": len(passed_with_scores),
        "passed": len(result_products),
        "imported": imported,
        "products": result_products[:100],
        "adapters_used": [r["supplier_id"] for r in list_registered() if r["available"]],
    }


def _save_raw_products(products) -> None:
    """NormalizedProduct 목록을 supplier_raw_products 테이블에 저장 (중복 스킵)."""
    with get_db() as db:
        for p in products:
            exists = db.query(SupplierRawProduct).filter_by(
                supplier_id=p.supplier_id, raw_id=p.raw_id
            ).first()
            if exists:
                continue
            moq_field = {
                "domeggook": "min_order_qty",
                "domemai": "minimumQty",
                "onchannel": "buyCnt",
            }.get(p.supplier_id, "moq")

            db.add(SupplierRawProduct(
                supplier_id=p.supplier_id,
                raw_id=p.raw_id,
                raw_url=p.raw_url,
                raw_name=p.name[:400],
                raw_price=p.supply_price,
                raw_moq_field=moq_field,
                raw_moq_value=p.moq,
                raw_stock=p.stock,
                raw_json=p.raw_json(),
            ))
        db.commit()


def _deduplicate_normalized(products) -> list:
    """NormalizedProduct 이름 기반 중복 제거 — 동일 상품은 최저가 공급처 선택."""
    import re

    def normalize(name: str) -> str:
        name = re.sub(r"[^\w가-힣]", " ", name.lower())
        return " ".join(name.split())

    groups: dict[str, list] = {}
    for p in products:
        key = normalize(p.name)[:30]
        groups.setdefault(key, []).append(p)

    result = []
    for group in groups.values():
        best = min(group, key=lambda x: x.supply_price)
        result.append(best)

    return result


# ── AI 콘텐츠 확장 (키워드·FAQ 생성) ──────────────────────────────────────────

def generate_product_keywords(product_id: int) -> dict:
    """상품에 대한 검색 키워드 10개를 생성한다.

    Returns: {"keywords": [str], "tags": [str]}
    """
    with get_db() as db:
        p = db.query(Product).filter_by(id=product_id).first()
        if not p:
            return {"keywords": [], "tags": []}

    from app.config import get_settings
    s = get_settings()

    if not s.claude_api_key:
        return {"keywords": [p.name], "tags": [p.category]}

    try:
        import anthropic, json as _json, re
        client = anthropic.Anthropic(api_key=s.claude_api_key)
        msg = client.messages.create(
            model=s.claude_model,
            max_tokens=500,
            messages=[{"role": "user", "content": f"""
한국 이커머스 SEO 전문가입니다. 아래 상품의 검색 키워드 10개와 태그 5개를 생성하세요.
상품명: {p.name}
카테고리: {p.category}
원산지: {p.origin}

JSON으로만 응답: {{"keywords":["키워드1","키워드2"...],"tags":["태그1"...]}}
"""}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = _json.loads(m.group())
            return {
                "keywords": data.get("keywords", [])[:10],
                "tags": data.get("tags", [])[:5],
            }
    except Exception as exc:
        logger.warning("키워드 생성 실패: %s", exc)

    return {"keywords": [p.name], "tags": [p.category]}


def generate_product_faq(product_id: int) -> list[dict]:
    """상품 FAQ 5개를 생성한다.

    Returns: [{"q": str, "a": str}]
    """
    with get_db() as db:
        p = db.query(Product).filter_by(id=product_id).first()
        if not p:
            return []

    from app.config import get_settings
    s = get_settings()

    if not s.claude_api_key:
        return [
            {"q": "배송은 얼마나 걸리나요?", "a": "주문 후 1~3 영업일 내 출고됩니다."},
            {"q": "교환·반품이 가능한가요?", "a": "수령 후 7일 이내 고객센터로 연락 주세요."},
        ]

    try:
        import anthropic, json as _json, re
        client = anthropic.Anthropic(api_key=s.claude_api_key)
        msg = client.messages.create(
            model=s.claude_model,
            max_tokens=800,
            messages=[{"role": "user", "content": f"""
한국 이커머스 CS 전문가입니다. 아래 상품의 자주묻는질문(FAQ) 5개를 작성하세요.
상품명: {p.name}
카테고리: {p.category}
원산지: {p.origin}

JSON 배열로만 응답: [{{"q":"질문1","a":"답변1"}},...]
"""}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            return _json.loads(m.group())[:5]
    except Exception as exc:
        logger.warning("FAQ 생성 실패: %s", exc)

    return [
        {"q": "배송은 얼마나 걸리나요?", "a": "주문 후 1~3 영업일 내 출고됩니다."},
        {"q": "교환·반품이 가능한가요?", "a": "수령 후 7일 이내 고객센터로 연락 주세요."},
    ]


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _platform_order_to_dict(po: PlatformOrder) -> dict:
    return {
        "id": po.id,
        "platform": po.platform,
        "platform_order_id": po.platform_order_id,
        "platform_item_id": po.platform_item_id,
        "product_id": po.product_id,
        "product_name": po.product_name,
        "quantity": po.quantity,
        "unit_price": float(po.unit_price or 0),
        "buyer_name": po.buyer_name,
        "receiver_name": po.receiver_name,
        "shipping_address": po.shipping_address,
        "receiver_phone": po.receiver_phone,
        "shipping_message": po.shipping_message,
        "status": po.status,
        "supplier": po.supplier,
        "tracking_number": po.tracking_number,
        "delivery_company": po.delivery_company,
        "invoice_registered": po.invoice_registered,
        "ordered_at": po.ordered_at.strftime("%Y-%m-%d %H:%M") if po.ordered_at else "",
        "shipped_at": po.shipped_at.strftime("%Y-%m-%d %H:%M") if po.shipped_at else "",
    }


# ── 공급사 워크플로우 엔진 연동 ────────────────────────────────────────────────────

def run_supplier_workflow(supplier_id: str, products=None, min_score: float = 80.0) -> dict:
    """공급사 상품 목록을 수집하고 워크플로우 상태 머신을 구동한다.

    Returns: {"created": int, "scored": int, "passed": int, "workflow_state": dict}
    """
    from app.suppliers.workflow import WFState, create_workflow_item, transition
    from app.ai_scoring import score_product, HARD_FILTERS

    if products is None:
        # 어댑터에서 직접 수집 (키워드 없이 최신 상품 목록)
        from app.suppliers.registry import get_adapter
        adapter = get_adapter(supplier_id)
        if not adapter:
            return {"ok": False, "error": f"등록되지 않은 공급사: {supplier_id}"}
        try:
            products = adapter.search("", page=1, limit=100, moq=HARD_FILTERS["moq_max"])
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    stats = {"created": 0, "scored": 0, "passed": 0, "rejected": 0}

    for p in products:
        # 워크플로우 아이템 생성 (중복 무시)
        item = create_workflow_item(
            supplier_id=supplier_id,
            raw_id=p.raw_id,
            product_name=p.name,
            supply_price=p.supply_price,
        )
        if item.workflow_state != WFState.DISCOVERED:
            continue  # 이미 처리된 상품 건너뜀
        stats["created"] += 1

        # AI 점수 계산
        score_result = score_product(p)
        stats["scored"] += 1

        # DB에 점수 저장
        with get_db() as db:
            wf = db.query(SupplierWorkflowItem).filter_by(id=item.id).first()
            if wf:
                import json as _json
                wf.ai_score = score_result.total
                wf.score_breakdown = _json.dumps(score_result.breakdown, ensure_ascii=False)
                db.commit()

        # DISCOVERED → AI_SCORED 전이
        transition(item.id, WFState.AI_SCORED,
                   extra={"score": score_result.total})

        # 점수 기반 분기
        from app.suppliers.workflow import requires_approval
        if score_result.total >= min_score:
            stats["passed"] += 1
            if not requires_approval(supplier_id):
                # 도매꾹/도매매: 바로 CONTENT_GENERATED로 진행
                transition(item.id, WFState.CONTENT_GENERATED,
                           extra={"auto_advance": True})
            # 온채널: batch_request_approvals()가 별도로 처리
        else:
            stats["rejected"] += 1
            if requires_approval(supplier_id):
                transition(item.id, WFState.SKIPPED,
                           error_msg=f"점수 미달: {score_result.total:.1f} < {min_score}")
            else:
                transition(item.id, WFState.REJECTED,
                           error_msg=f"점수 미달: {score_result.total:.1f} < {min_score}")

    return {**stats, "supplier_id": supplier_id}


def process_onchannel_approvals(min_score: float = 80.0, limit: int = 20) -> dict:
    """AI_SCORED 상태 온채널 상품에 대해 일괄 판매신청을 요청한다."""
    from app.suppliers.onchannel_approval import batch_request_approvals
    return batch_request_approvals(min_score=min_score, limit=limit)


def monitor_onchannel_approvals(limit: int = 50) -> dict:
    """APPROVAL_REQUESTED 상태 온채널 상품의 승인 결과를 폴링한다."""
    from app.suppliers.onchannel_approval import monitor_approvals
    result = monitor_approvals(limit=limit)

    # 승인된 상품을 CONTENT_GENERATED로 자동 전이
    if result.get("approved", 0) > 0:
        from app.suppliers.workflow import WFState, get_workflow_items, transition
        approved_items = get_workflow_items(supplier_id="onchannel", state=WFState.APPROVED)
        for item_dict in approved_items:
            t = transition(item_dict["id"], WFState.CONTENT_GENERATED,
                           extra={"auto_advance": True})
            if not t["ok"]:
                logger.warning("온채널 CONTENT 전이 실패: %s", t)

    return result


def get_workflow_status(supplier_id: str = "") -> dict:
    """공급사별 워크플로우 현황 대시보드 데이터를 반환한다."""
    from app.suppliers.workflow import get_workflow_stats, get_workflow_items, WFState

    stats = get_workflow_stats()

    # 최근 변경 아이템 목록 (액션 필요한 것 우선)
    action_needed = []
    if not supplier_id or supplier_id == "onchannel":
        # 온채널: APPROVAL_PENDING (신청 미완료), APPROVED (콘텐츠 생성 필요)
        pending = get_workflow_items("onchannel", WFState.APPROVAL_PENDING, limit=10)
        approved = get_workflow_items("onchannel", WFState.APPROVED, limit=10)
        action_needed.extend([{**i, "action": "판매신청 필요"} for i in pending])
        action_needed.extend([{**i, "action": "콘텐츠 생성 필요"} for i in approved])

    for sid in ["domeggook", "domemai"]:
        if not supplier_id or supplier_id == sid:
            content_items = get_workflow_items(sid, WFState.CONTENT_GENERATED, limit=5)
            action_needed.extend([{**i, "action": "플랫폼 등록 필요"} for i in content_items])

    return {
        "stats": stats,
        "action_needed": action_needed[:20],
        "supplier_id": supplier_id or "all",
    }


# ── 성과 분석 · 생존율 엔진 · 자동 교체 ─────────────────────────────────────────

def collect_product_performance(platform: str = "all", days_back: int = 1) -> dict:
    """플랫폼 성과 데이터를 수집해 product_performance 테이블에 저장한다."""
    from app.analytics.performance import collect_performance
    return collect_performance(platform=platform, days_back=days_back)


def run_survival_analysis(window_days: int = 7, platform: str = "all") -> dict:
    """등록 상품 생존율 분석 (7/14/30일 윈도우).

    Returns: {"window_days": int, "total": int, "healthy": int, "watch": int,
              "delete_candidates": int, "items": list}
    """
    from app.analytics.performance import (
        run_survival_analysis as _run_survival,
        STATUS_HEALTHY, STATUS_WATCH, STATUS_DELETE,
    )

    items = _run_survival(window_days=window_days, platform=platform)
    return {
        "window_days": window_days,
        "total": len(items),
        "healthy": sum(1 for i in items if i["status"] == STATUS_HEALTHY),
        "watch": sum(1 for i in items if i["status"] == STATUS_WATCH),
        "delete_candidates": sum(1 for i in items if i["status"] == STATUS_DELETE),
        "items": items,
    }


def auto_replace_dead_products(
    window_days: int = 14,
    platform: str = "all",
    replacement_source: str = "domeggook",
    dry_run: bool = False,
) -> dict:
    """성과 미달(DELETE_CANDIDATE) 상품을 삭제하고 신규 상품으로 교체한다.

    [교체 순환 로직]
      1. DELETE_CANDIDATE 목록 수집
      2. 플랫폼 상품 삭제 (Listing 상태 → deleted)
      3. bulk_collect_and_score()로 교체 후보 수집
      4. 교체 상품 import + upload
    """
    from app.analytics.performance import (
        get_delete_candidates, mark_as_delisted
    )
    from app.db import get_db, Listing, Product

    candidates = get_delete_candidates(platform=platform, window_days=window_days)
    stats = {
        "candidates": len(candidates),
        "delisted": 0, "replaced": 0,
        "errors": 0, "dry_run": dry_run,
    }

    if dry_run:
        stats["candidates_preview"] = [
            {"product_id": c["product_id"], "reason": c["reason"],
             "survival_score": c["survival_score"]}
            for c in candidates[:10]
        ]
        return stats

    delisted_product_ids = []
    for c in candidates:
        pid = c["product_id"]
        plat = c["platform"]

        try:
            # 플랫폼 리스팅 비활성화
            with get_db() as db:
                listing = db.query(Listing).filter_by(
                    product_id=pid, platform=plat, status="success"
                ).first()
                if listing:
                    listing.status = "delisted"
                    db.commit()

            mark_as_delisted(pid, plat)
            delisted_product_ids.append(pid)
            stats["delisted"] += 1
            logger.info("삭제 완료: product_id=%d platform=%s reason=%s",
                        pid, plat, c["reason"])

        except Exception as exc:
            logger.error("삭제 실패 product_id=%d: %s", pid, exc)
            stats["errors"] += 1

    # 삭제된 수만큼 신규 상품 교체
    if delisted_product_ids:
        try:
            replacement_result = bulk_collect_and_score(
                sources=[replacement_source],
                limit_per_kw=30,
                min_score=82,           # 교체 상품은 더 높은 기준
                min_margin_pct=0.28,
                auto_import=True,
                max_import=len(delisted_product_ids),
            )
            stats["replaced"] = replacement_result.get("imported", 0)
        except Exception as exc:
            logger.error("교체 상품 수집 실패: %s", exc)
            stats["errors"] += 1

    return stats


def scan_stockout_risks(auto_exclude: bool = True) -> dict:
    """전체 상품 품절 위험 스캔 → CRITICAL 상품 자동 제외."""
    from app.analytics.stockout_predictor import scan_all_products
    result = scan_all_products(auto_exclude_critical=auto_exclude)

    # CRITICAL 상품이 있으면 텔레그램 알림
    if result.get("critical", 0) > 0:
        from app.analytics.stockout_predictor import get_high_risk_products
        from app.notify.events import notify, NotifyLevel, EventType
        try:
            high_risk = get_high_risk_products(limit=5)
            lines = "\n".join(
                f"• {r['product_name'][:25]} — 잔여{r['days_until_stockout']}일 [{r['risk_level']}]"
                for r in high_risk
            )
            notify(
                level=NotifyLevel.CRITICAL,
                title=f"품절위험 CRITICAL {result['critical']}개",
                body=lines,
                event_type=EventType.STOCK_LOW,
            )
        except Exception:
            pass

    return result


def rank_collected_products(
    products=None,
    supplier_ids: list[str] | None = None,
    top_pct: float = 0.05,
    keywords: list[str] | None = None,
) -> list[dict]:
    """수집된 상품 목록에 6차원 랭킹 점수를 계산하고 상위 top_pct를 반환한다.

    products: list[NormalizedProduct] — 없으면 supplier_ids에서 수집
    """
    from app.analytics.ranking import rank_products

    if products is None:
        from app.suppliers.registry import get_available_adapters
        adapters = get_available_adapters()
        products = []
        for adapter in adapters:
            if supplier_ids and adapter.supplier_id not in supplier_ids:
                continue
            try:
                for kw in (keywords or [""])[:2]:
                    products.extend(adapter.search(kw, limit=100))
            except Exception as exc:
                logger.warning("수집 실패 [%s]: %s", adapter.supplier_id, exc)

    top = rank_products(products, top_pct=top_pct, keywords=keywords)
    return [{
        "supplier_id": p.supplier_id,
        "raw_id": p.raw_id,
        "name": p.name,
        "supply_price": p.supply_price,
        "moq": p.moq,
        "lead_time_days": p.lead_time_days,
        "ranking_score": rs.total,
        "rank_tier": rs.rank_tier,
        "breakdown": rs.breakdown,
        "recommendation": rs.recommendation,
    } for p, rs in top]


def get_performance_dashboard() -> dict:
    """성과 분석 · 생존율 · 품절위험 통합 대시보드 데이터."""
    from app.analytics.performance import get_survival_dashboard
    from app.analytics.stockout_predictor import get_risk_summary

    survival = get_survival_dashboard()
    risk = get_risk_summary()

    # 최근 7일 DELETE_CANDIDATE 수
    from app.db import get_db, ProductSurvivalStatus
    from datetime import date
    with get_db() as db:
        delete_count = db.query(ProductSurvivalStatus).filter(
            ProductSurvivalStatus.status == "DELETE_CANDIDATE",
            ProductSurvivalStatus.auto_action == "",
        ).count()

    return {
        "survival": survival,
        "stockout_risk": risk,
        "pending_deletion": delete_count,
    }


# ── SEO 최적화 (기존 등록 상품 검색 최적화) ──────────────────────────────────────
# 실제 로직은 app/seo/ 패키지에 있음. 여기서는 다른 탭들과 동일하게 얇은 래퍼만 제공.

def list_seo_target_products(platform: str) -> list[dict]:
    """플랫폼에 성공적으로 등록되어 SEO 분석 대상이 되는 상품 목록."""
    with get_db() as db:
        product_ids = [
            l.product_id for l in
            db.query(Listing).filter_by(platform=platform, status="success").all()
        ]
        if not product_ids:
            return []
        products = db.query(Product).filter(Product.id.in_(product_ids)).all()
        return [{"id": p.id, "name": p.name, "category": p.category,
                 "sell_price": float(p.sell_price)} for p in products]


def run_seo_analysis(product_ids: list[int], platform: str, competitor_url: str = "") -> list[dict]:
    """선택한 상품들에 대해 SEO 분석/제안(SeoRevision, status=DRAFT)을 생성한다."""
    from app.seo.revision_service import analyze_product
    return [analyze_product(pid, platform, competitor_url) for pid in product_ids]


def list_seo_revisions(status: str = "", platform: str = "") -> list[dict]:
    from app.seo.revision_service import list_revisions
    return list_revisions(status=status, platform=platform)


def get_seo_revision(revision_id: int) -> dict | None:
    from app.seo.revision_service import get_revision
    return get_revision(revision_id)


def approve_seo_revision(revision_id: int, reviewer: str = "") -> dict:
    from app.seo.revision_service import approve_revision
    return approve_revision(revision_id, reviewer)


def reject_seo_revision(revision_id: int, reason: str = "", reviewer: str = "") -> dict:
    from app.seo.revision_service import reject_revision
    return reject_revision(revision_id, reason, reviewer)


def apply_seo_revision(revision_id: int) -> dict:
    """승인된 SEO 제안을 라이브 상품에 반영한다 (스마트스토어만 자동 반영 가능)."""
    from app.seo.revision_service import apply_revision
    return apply_revision(revision_id)


def get_seo_before_after(product_id: int, platform: str) -> dict:
    """가장 최근 APPLIED 이력을 기준으로 반영 전/후 CTR·CVR·매출을 비교한다."""
    from app.db import ProductPerformance
    from app.seo.revision_service import list_revisions

    applied = [
        r for r in list_revisions(platform=platform)
        if r["product_id"] == product_id and r["status"] == "APPLIED" and r["applied_at"]
    ]
    if not applied:
        return {"ok": False, "error": "적용된 SEO 변경 이력이 없습니다"}

    applied.sort(key=lambda r: r["applied_at"], reverse=True)
    applied_date = applied[0]["applied_at"].strftime("%Y-%m-%d")

    def _avg(rows, field):
        return round(sum(getattr(r, field) for r in rows) / len(rows), 4) if rows else 0.0

    with get_db() as db:
        before = db.query(ProductPerformance).filter(
            ProductPerformance.product_id == product_id,
            ProductPerformance.platform == platform,
            ProductPerformance.snapshot_date < applied_date,
        ).order_by(ProductPerformance.snapshot_date.desc()).limit(14).all()
        after = db.query(ProductPerformance).filter(
            ProductPerformance.product_id == product_id,
            ProductPerformance.platform == platform,
            ProductPerformance.snapshot_date >= applied_date,
        ).order_by(ProductPerformance.snapshot_date.asc()).limit(14).all()

    return {
        "ok": True,
        "applied_at": applied_date,
        "before": {"days": len(before), "avg_ctr": _avg(before, "ctr"), "avg_cvr": _avg(before, "cvr"),
                   "total_orders": sum(r.orders for r in before), "total_revenue": sum(r.revenue for r in before)},
        "after": {"days": len(after), "avg_ctr": _avg(after, "ctr"), "avg_cvr": _avg(after, "cvr"),
                  "total_orders": sum(r.orders for r in after), "total_revenue": sum(r.revenue for r in after)},
    }


def export_seo_revisions_csv(status: str = "", platform: str = "") -> str:
    """SEO 제안 목록을 CSV 문자열로 변환한다 (쿠팡 등 수동 반영 플랫폼용)."""
    import pandas as pd
    from app.seo.revision_service import list_revisions

    rows = [{
        "product_id": r["product_id"], "platform": r["platform"], "status": r["status"],
        "original_name": r["original_name"],
        "suggested_name": r["suggested_names"][0] if r["suggested_names"] else "",
        "suggested_keywords": ", ".join(r["suggested_keywords"]),
        "score_before": r["score_before"], "score_after": r["score_after"],
    } for r in list_revisions(status=status, platform=platform)]
    return pd.DataFrame(rows).to_csv(index=False)


# ── 카탈로그 동기화 (플랫폼에 이미 등록된 상품 → 로컬 DB) ────────────────────────

def sync_platform_catalog(platform: str) -> dict:
    """플랫폼에 이미 등록된 상품을 로컬 DB로 가져온다 (읽기 전용, 플랫폼에는 쓰지 않음).

    이 앱을 거치지 않고 판매자센터에서 직접 등록한 상품도 여기서 채워지므로,
    SEO 분석 등 다른 기능이 실제 카탈로그 전체를 대상으로 동작할 수 있게 된다.

    Returns: {"ok": bool, "total_found": int, "created": int, "linked": int,
              "skipped": int} 또는 실패 시 {"ok": False, "error": str}
    """
    from app.sync.catalog_sync import sync_coupang_catalog, sync_smartstore_catalog
    if platform == "coupang":
        return sync_coupang_catalog()
    elif platform == "smartstore":
        return sync_smartstore_catalog()
    return {"ok": False, "error": f"알 수 없는 플랫폼: {platform}"}
