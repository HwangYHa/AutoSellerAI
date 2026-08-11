"""Notification Events — 이벤트 타입 정의, 메시지 포매터, 발송 진입점."""
from __future__ import annotations
import logging
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class NotifyLevel(str, Enum):
    CRITICAL = "critical"
    WARNING  = "warning"
    INFO     = "info"
    SUCCESS  = "success"


class EventType(str, Enum):
    # 상품·업로드
    UPLOAD_SUCCESS    = "upload_success"
    UPLOAD_FAILED     = "upload_failed"
    PIPELINE_DONE     = "pipeline_done"
    # 주문·배송
    ORDER_NEW         = "order_new"
    ORDER_SHIPPED     = "order_shipped"
    # 재고·발주
    STOCK_LOW         = "stock_low"
    INVENTORY_CRITICAL = "inventory_critical"
    INVENTORY_WARNING  = "inventory_warning"
    PO_CREATED        = "po_created"
    PO_RECEIVED       = "po_received"
    # 정산·리포트
    DAILY_REPORT      = "daily_report"
    # 시스템
    SYSTEM_TEST       = "system_test"
    SYSTEM_ERROR      = "system_error"


_LEVEL_EMOJI = {
    NotifyLevel.CRITICAL: "🚨",
    NotifyLevel.WARNING:  "⚠️",
    NotifyLevel.INFO:     "ℹ️",
    NotifyLevel.SUCCESS:  "✅",
}

_LEVEL_HEADER = {
    NotifyLevel.CRITICAL: "🚨 <b>[위험]</b>",
    NotifyLevel.WARNING:  "⚠️ <b>[주의]</b>",
    NotifyLevel.INFO:     "ℹ️ <b>[정보]</b>",
    NotifyLevel.SUCCESS:  "✅ <b>[성공]</b>",
}


def _now_kst() -> str:
    from datetime import timezone, timedelta
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")


def format_message(
    level: NotifyLevel,
    title: str,
    body: str,
    event_type: str = "",
) -> str:
    """HTML 형식 Telegram 메시지 조립."""
    header = _LEVEL_HEADER.get(level, "")
    footer = f"\n<i>⏰ {_now_kst()} · AutoSeller AI</i>"
    return f"{header} {title}\n\n{body}{footer}"


# ── 이벤트별 메시지 빌더 ──────────────────────────────────────────────────────

def build_upload_success(platform: str, product_name: str, platform_id: str) -> str:
    plat_lbl = {"coupang": "쿠팡", "smartstore": "스마트스토어"}.get(platform, platform)
    return (
        f"플랫폼: <b>{plat_lbl}</b>\n"
        f"상품: <code>{product_name[:50]}</code>\n"
        f"상품번호: <code>{platform_id}</code>"
    )


def build_upload_failed(platform: str, product_name: str, error: str) -> str:
    plat_lbl = {"coupang": "쿠팡", "smartstore": "스마트스토어"}.get(platform, platform)
    return (
        f"플랫폼: <b>{plat_lbl}</b>\n"
        f"상품: <code>{product_name[:50]}</code>\n"
        f"오류: <code>{error[:200]}</code>"
    )


def build_pipeline_done(
    collected: int, passed: int, imported: int, ok: int, fail: int
) -> str:
    return (
        f"수집 <b>{collected}</b>개 → 마진통과 <b>{passed}</b>개\n"
        f"DB 등록 <b>{imported}</b>개\n"
        f"업로드 성공 <b>{ok}</b>건 / 실패 <b>{fail}</b>건"
    )


def build_inventory_critical(items: list[dict]) -> str:
    lines = []
    for it in items[:8]:
        lines.append(
            f"• <b>{it['product_name'][:30]}</b> — "
            f"가용 <b>{it['available_qty']}</b>개 "
            f"(안전재고 {it['safety_stock']}개)"
        )
    suffix = f"\n<i>+{len(items)-8}개 더</i>" if len(items) > 8 else ""
    return "\n".join(lines) + suffix


def build_inventory_warning(items: list[dict]) -> str:
    lines = []
    for it in items[:5]:
        days = it.get("days_of_stock", -1)
        days_str = f"{days:.0f}일분" if days >= 0 else "∞"
        lines.append(
            f"• <b>{it['product_name'][:30]}</b> — "
            f"가용 {it['available_qty']}개 ({days_str} 남음) "
            f"→ 추천 발주 <b>{it['suggested_qty']}</b>개"
        )
    suffix = f"\n<i>+{len(items)-5}개 더</i>" if len(items) > 5 else ""
    return "\n".join(lines) + suffix


def build_po_created(po_number: str, supplier: str, item_count: int, total: float) -> str:
    return (
        f"발주번호: <code>{po_number}</code>\n"
        f"공급처: <b>{supplier or '미지정'}</b>\n"
        f"상품 {item_count}종 · 총액 <b>{total:,.0f}원</b>"
    )


def build_po_received(po_number: str, item_count: int) -> str:
    return (
        f"발주번호: <code>{po_number}</code>\n"
        f"{item_count}종 상품 입고 완료 — 재고에 반영되었습니다."
    )


def build_daily_report(dashboard: dict) -> str:
    sm = dashboard.get("summary", {})
    by_plat = dashboard.get("by_platform", {})
    cp = by_plat.get("coupang", {})
    ss = by_plat.get("smartstore", {})
    tax = dashboard.get("tax_estimate", {})

    month = dashboard.get("month", "?")
    year = dashboard.get("year", "?")

    return (
        f"📅 <b>{year}년 {month}월 현황</b>\n\n"
        f"주문 <b>{sm.get('order_count',0)}</b>건\n"
        f"총매출 <b>{sm.get('gross_revenue',0):,.0f}원</b>\n"
        f"순이익 <b>{sm.get('net_profit',0):,.0f}원</b> "
        f"(마진 {sm.get('margin_rate',0):.1%})\n\n"
        f"🟡 쿠팡: {cp.get('order_count',0)}건 · "
        f"{cp.get('net_profit',0):,.0f}원\n"
        f"🟢 스마트스토어: {ss.get('order_count',0)}건 · "
        f"{ss.get('net_profit',0):,.0f}원\n\n"
        f"🏛️ 부가세 {sm.get('vat_payable',0):,.0f}원\n"
        f"📑 연간 세금 추정 {tax.get('total_tax',0):,.0f}원"
    )


# ── 발송 진입점 ───────────────────────────────────────────────────────────────

def notify(
    level: NotifyLevel | str,
    title: str,
    body: str,
    event_type: str = EventType.SYSTEM_TEST,
    save_log: bool = True,
) -> bool:
    """알림 발송 통합 진입점. 실패해도 예외를 올리지 않는다."""
    from app.notify.telegram import get_bot

    if isinstance(level, str):
        level = NotifyLevel(level)

    text = format_message(level, title, body, event_type)
    result = get_bot().send_message(text)

    if save_log:
        _save_log(
            event_type=str(event_type),
            level=str(level.value),
            title=title,
            body=body[:500],
            status="ok" if result["ok"] else "failed",
            error=result.get("error", ""),
        )

    if not result["ok"]:
        logger.warning("알림 발송 실패 [%s]: %s", event_type, result.get("error"))
    return result["ok"]


def _save_log(
    event_type: str, level: str, title: str, body: str,
    status: str, error: str
) -> None:
    try:
        from app.db import get_db, NotificationLog
        with get_db() as db:
            db.add(NotificationLog(
                event_type=event_type,
                level=level,
                title=title,
                body=body,
                status=status,
                error=error[:300],
            ))
            db.commit()
    except Exception as exc:
        logger.error("알림 로그 저장 실패: %s", exc)
