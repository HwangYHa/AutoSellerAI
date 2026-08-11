"""Cron Job 함수 정의 — APScheduler에서 호출되는 실제 작업 로직."""
from __future__ import annotations
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── 기본 작업 설정 (DB 초기화 시 사용) ───────────────────────────────────────

DEFAULT_JOBS: dict[str, dict] = {
    "pipeline_auto": {
        "name": "자동 파이프라인",
        "description": "온채널 수집 → AI 최적화 → 쿠팡·스마트스토어 업로드",
        "cron_expr": "0 3 * * *",       # 매일 03:00 KST
        "enabled": False,
    },
    "inventory_check": {
        "name": "재고 위험 체크",
        "description": "재고 critical/warning 스캔 → 텔레그램 알림",
        "cron_expr": "0 * * * *",        # 매시간 정각
        "enabled": False,
    },
    "daily_report": {
        "name": "일일 정산 리포트",
        "description": "이번 달 매출·순이익·세금 요약 텔레그램 전송",
        "cron_expr": "0 21 * * *",       # 매일 21:00 KST
        "enabled": False,
    },
    "market_refresh": {
        "name": "시장 분석 자동 갱신",
        "description": "최근 분석한 키워드(최대 5개) 자동 재분석",
        "cron_expr": "0 9 * * 1",        # 매주 월요일 09:00 KST
        "enabled": False,
    },
    "price_optimize": {
        "name": "가격 최적화 점검",
        "description": "등록 상품 마진 재계산 → 기준 미달 상품 텔레그램 경고",
        "cron_expr": "0 6 * * *",        # 매일 06:00 KST
        "enabled": False,
    },
    "order_collect": {
        "name": "주문 자동 수집",
        "description": "쿠팡·스마트스토어 신규 주문 수집 → DB 저장 → 텔레그램 알림",
        "cron_expr": "*/5 * * * *",      # 5분마다
        "enabled": False,
    },
    "stock_sync": {
        "name": "재고 플랫폼 동기화",
        "description": "내부 재고 → 쿠팡·스마트스토어 재고 수량 자동 업데이트",
        "cron_expr": "*/30 * * * *",     # 30분마다
        "enabled": False,
    },
    "price_sync": {
        "name": "가격 플랫폼 동기화",
        "description": "목표 마진 기준 재계산 후 쿠팡·스마트스토어 가격 업데이트",
        "cron_expr": "0 */2 * * *",      # 2시간마다
        "enabled": False,
    },
    "bulk_collect": {
        "name": "대량 상품 수집 선별",
        "description": "3개 공급사 대량 수집 → 중복제거 → AI 80점 필터 → 보고서",
        "cron_expr": "0 2 * * 1",        # 매주 월요일 02:00 KST
        "enabled": False,
    },
    "onchannel_approval_monitor": {
        "name": "온채널 승인 모니터링",
        "description": "판매신청 대기 상품의 공급사 승인 결과 자동 폴링 → 상태 전이",
        "cron_expr": "*/30 * * * *",     # 30분마다
        "enabled": False,
    },
    "performance_collect": {
        "name": "성과 데이터 수집",
        "description": "쿠팡·스마트스토어 판매 성과(주문·매출) 일별 스냅샷 수집",
        "cron_expr": "0 1 * * *",        # 매일 01:00 KST
        "enabled": False,
    },
    "survival_analysis": {
        "name": "상품 생존율 분석",
        "description": "7/14/30일 CTR·CVR 기준 생존 판정 → DELETE_CANDIDATE 분류",
        "cron_expr": "0 4 * * 1",        # 매주 월요일 04:00 KST
        "enabled": False,
    },
    "auto_replace": {
        "name": "성과미달 상품 자동 교체",
        "description": "DELETE_CANDIDATE 상품 삭제 → 신규 AI 선별 상품으로 교체",
        "cron_expr": "0 5 * * 1",        # 매주 월요일 05:00 KST (survival_analysis 직후)
        "enabled": False,
    },
    "stockout_scan": {
        "name": "품절 위험 스캔",
        "description": "재고·판매속도 분석 → CRITICAL 상품 자동 품절처리 + 텔레그램 경고",
        "cron_expr": "0 */4 * * *",      # 4시간마다
        "enabled": False,
    },
}


# ── 작업 함수 ─────────────────────────────────────────────────────────────────

def job_pipeline_auto() -> dict:
    """온채널 키워드 수집 → AI 최적화 → 플랫폼 업로드 전자동화."""
    from app.pipeline import (
        list_products, import_product, upload_product, notify_pipeline_done
    )
    from app.config import get_settings
    s = get_settings()

    # 설정: 온채널로 고정, 기존 상품 수가 적을 때만 실행
    existing = list_products()["total"]
    if existing >= 500:
        return {"skipped": True, "reason": f"상품 수 {existing}개 초과 — 수동 실행 필요"}

    # 저장된 최근 수집 키워드 재활용 (market_insights 테이블)
    from app.db import get_db, MarketInsight
    with get_db() as db:
        from sqlalchemy import desc
        recent = (
            db.query(MarketInsight)
            .order_by(desc(MarketInsight.analyzed_at))
            .limit(3)
            .all()
        )
        keywords = [r.keyword for r in recent]

    if not keywords:
        keywords = ["텀블러"]   # 기본 키워드

    collected = passed = imported = ok = fail = 0

    for kw in keywords[:2]:   # 최대 2개 키워드 (배치 시간 절약)
        try:
            from app.suppliers.onchannel import search as _s
            prods = _s(keyword=kw, limit=10)
            collected += len(prods)

            fee_max = 0.108
            ship = 3000
            mult = 3.5

            for prod in prods:
                if prod.supply_price <= 0:
                    continue
                sell = prod.supply_price * mult
                margin = (sell - prod.supply_price - ship - sell * fee_max) / sell
                if margin < s.min_margin_pct:
                    continue
                passed += 1
                res = import_product(prod.source, prod.source_id, int(sell), True)
                if res["status"] in ("imported", "updated"):
                    imported += 1
                    for r in upload_product(res["id"], ["coupang", "smartstore"]):
                        if r["status"] == "success":
                            ok += 1
                        else:
                            fail += 1
        except Exception as exc:
            logger.error("pipeline_auto 키워드 '%s' 오류: %s", kw, exc)

    notify_pipeline_done(collected, passed, imported, ok, fail)
    return {
        "keywords": keywords[:2],
        "collected": collected, "passed": passed,
        "imported": imported, "ok": ok, "fail": fail,
    }


def job_inventory_check() -> dict:
    """재고 위험·경고 스캔 → 텔레그램 알림."""
    from app.pipeline import trigger_inventory_alerts
    result = trigger_inventory_alerts()
    return result


def job_daily_report() -> dict:
    """이번 달 정산 리포트 텔레그램 전송."""
    from app.pipeline import send_daily_report
    return send_daily_report()


def job_market_refresh() -> dict:
    """최근 분석 키워드 상위 5개를 자동 재분석."""
    from app.pipeline import analyze_market, get_market_history
    history = get_market_history(limit=5)
    refreshed = failed = 0
    for h in history:
        try:
            analyze_market(h["keyword"], force_refresh=True)
            refreshed += 1
        except Exception as exc:
            logger.error("market_refresh '%s': %s", h["keyword"], exc)
            failed += 1
    return {"refreshed": refreshed, "failed": failed}


def job_price_optimize() -> dict:
    """판매 중 상품 마진 점검 → 기준 미달 시 텔레그램 경고."""
    from app.pipeline import list_products
    from app.notify.events import notify, NotifyLevel, EventType
    from app.config import get_settings
    s = get_settings()

    items = list_products(status="listed", limit=200)["items"]
    low_margin = []

    for p in items:
        sp = p["supply_price"]
        sell = p["sell_price"]
        if sp <= 0 or sell <= 0:
            continue
        fee = 0.108
        ship = 3000
        margin = (sell - sp - ship - sell * fee) / sell
        if margin < s.min_margin_pct:
            low_margin.append({
                "name": p["name"][:40],
                "sku": p["sku"],
                "margin": margin,
            })

    if low_margin:
        lines = "\n".join(
            f"• {it['name']} — 마진 {it['margin']:.1%}" for it in low_margin[:8]
        )
        notify(
            level=NotifyLevel.WARNING,
            title=f"마진 기준 미달 상품 {len(low_margin)}개",
            body=lines,
            event_type=EventType.SYSTEM_ERROR,
        )

    return {"checked": len(items), "low_margin": len(low_margin)}


def job_order_collect() -> dict:
    """쿠팡·스마트스토어 신규 주문 수집 (5분 주기)."""
    from app.pipeline import collect_platform_orders
    return collect_platform_orders(hours_back=1)


def job_stock_sync() -> dict:
    """내부 재고 → 플랫폼 재고 동기화 (30분 주기)."""
    from app.pipeline import sync_platform_inventory
    result = sync_platform_inventory()
    if result["updated"] > 0 or result["failed"] > 0:
        from app.notify.events import notify, NotifyLevel, EventType
        try:
            notify(
                level=NotifyLevel.INFO if result["failed"] == 0 else NotifyLevel.WARNING,
                title=f"재고 동기화 완료 — 성공 {result['updated']}건",
                body=f"실패 {result['failed']}건 / 건너뜀 {result['skipped']}건",
                event_type=EventType.STOCK_LOW,
            )
        except Exception:
            pass
    return result


def job_price_sync() -> dict:
    """목표 마진 기준 가격 재계산 → 플랫폼 가격 동기화 (2시간 주기)."""
    from app.pipeline import sync_prices_to_platforms
    result = sync_prices_to_platforms()
    if result["updated"] > 0:
        from app.notify.events import notify, NotifyLevel, EventType
        try:
            notify(
                level=NotifyLevel.INFO,
                title=f"가격 동기화 완료 — {result['updated']}개 상품 업데이트",
                body=f"실패 {result['failed']}건 / 건너뜀 {result['skipped']}건",
                event_type=EventType.SYSTEM_ERROR,
            )
        except Exception:
            pass
    return result


def job_bulk_collect() -> dict:
    """3개 공급사 대량 수집 → 중복제거 → AI 선별 → 텔레그램 보고 (주 1회)."""
    from app.pipeline import bulk_collect_and_score
    from app.notify.events import notify, NotifyLevel, EventType

    result = bulk_collect_and_score(
        sources=["onchannel", "domemai", "domeggook"],
        limit_per_kw=50,
        min_score=80,
        min_margin_pct=0.25,
        auto_import=False,
    )

    try:
        body_lines = []
        for p in result.get("products", [])[:5]:
            body_lines.append(
                f"• {p['name'][:30]} — {p['supply_price']:,}원 "
                f"(마진 {p.get('estimated_margin', 0):.0f}% / 점수 {p.get('score', 0)})"
            )
        notify(
            level=NotifyLevel.INFO,
            title=f"대량 선별 완료: 통과 {result['passed']}개",
            body=(
                f"수집 {result['collected']}개 → 중복제거 {result['deduped']}개 → "
                f"필터 {result['filtered']}개 → 80점↑ {result['passed']}개\n\n"
                "상위 5개:\n" + "\n".join(body_lines)
            ),
            event_type=EventType.PIPELINE_DONE,
        )
    except Exception:
        pass

    return result


def job_onchannel_approval_monitor() -> dict:
    """온채널 판매신청 대기 상품의 승인 결과를 폴링하고 워크플로우를 전이한다 (30분 주기)."""
    from app.pipeline import monitor_onchannel_approvals, process_onchannel_approvals
    from app.notify.events import notify, NotifyLevel, EventType

    # 1) 기존 APPROVAL_PENDING 상품 판매신청
    requested = process_onchannel_approvals(min_score=80.0, limit=20)

    # 2) APPROVAL_REQUESTED 상품 결과 폴링
    monitored = monitor_onchannel_approvals(limit=50)

    total_approved = monitored.get("approved", 0)
    total_rejected = monitored.get("rejected", 0)

    if total_approved > 0 or requested.get("requested", 0) > 0:
        try:
            notify(
                level=NotifyLevel.INFO,
                title=f"온채널 승인 모니터링 완료",
                body=(
                    f"신규신청: {requested.get('requested', 0)}건 | "
                    f"승인: {total_approved}건 | "
                    f"거절: {total_rejected}건 | "
                    f"대기: {monitored.get('pending', 0)}건"
                ),
                event_type=EventType.PIPELINE_DONE,
            )
        except Exception:
            pass

    return {
        "requested": requested,
        "monitored": monitored,
    }


def job_performance_collect() -> dict:
    """쿠팡·스마트스토어 판매 성과 일별 스냅샷 수집 (매일 01:00)."""
    from app.pipeline import collect_product_performance
    return collect_product_performance(platform="all", days_back=1)


def job_survival_analysis() -> dict:
    """상품 생존율 7/14/30일 분석 → DELETE_CANDIDATE 분류 (주 1회)."""
    from app.pipeline import run_survival_analysis
    from app.notify.events import notify, NotifyLevel, EventType

    results = {}
    for window in [7, 14, 30]:
        results[f"{window}d"] = run_survival_analysis(window_days=window)

    total_delete = sum(r["delete_candidates"] for r in results.values())
    if total_delete > 0:
        try:
            summary_lines = []
            for key, r in results.items():
                summary_lines.append(
                    f"[{key}] 정상:{r['healthy']} / 관찰:{r['watch']} / 삭제후보:{r['delete_candidates']}"
                )
            notify(
                level=NotifyLevel.WARNING if total_delete >= 5 else NotifyLevel.INFO,
                title=f"생존율 분석 완료 — 삭제후보 {total_delete}개",
                body="\n".join(summary_lines),
                event_type=EventType.PIPELINE_DONE,
            )
        except Exception:
            pass

    return results


def job_auto_replace() -> dict:
    """성과미달 상품 자동 삭제 + 신규 교체 (주 1회 — survival_analysis 직후)."""
    from app.pipeline import auto_replace_dead_products
    from app.notify.events import notify, NotifyLevel, EventType

    result = auto_replace_dead_products(
        window_days=14,
        dry_run=False,
        replacement_source="domeggook",
    )

    try:
        notify(
            level=NotifyLevel.INFO,
            title=f"상품 자동 교체 완료",
            body=(
                f"삭제후보 {result['candidates']}개 → "
                f"삭제 {result['delisted']}개 → "
                f"신규 교체 {result['replaced']}개"
            ),
            event_type=EventType.PIPELINE_DONE,
        )
    except Exception:
        pass

    return result


def job_stockout_scan() -> dict:
    """품절 위험 스캔 → CRITICAL 자동 제외 + 텔레그램 경고 (4시간 주기)."""
    from app.pipeline import scan_stockout_risks
    return scan_stockout_risks(auto_exclude=True)


# 작업 ID → 함수 매핑
JOB_FUNCTIONS: dict[str, callable] = {
    "pipeline_auto":                 job_pipeline_auto,
    "inventory_check":               job_inventory_check,
    "daily_report":                  job_daily_report,
    "market_refresh":                job_market_refresh,
    "price_optimize":                job_price_optimize,
    "order_collect":                 job_order_collect,
    "stock_sync":                    job_stock_sync,
    "price_sync":                    job_price_sync,
    "bulk_collect":                  job_bulk_collect,
    "onchannel_approval_monitor":    job_onchannel_approval_monitor,
    "performance_collect":           job_performance_collect,
    "survival_analysis":             job_survival_analysis,
    "auto_replace":                  job_auto_replace,
    "stockout_scan":                 job_stockout_scan,
}
