from __future__ import annotations

from typing import Any

from app.notify.events import EventType, NotifyLevel, notify
from app.pricing.approval_queue import sync_approval_queue
from app.pricing.service import get_policy, load_price_rows
from app.pricing.supply_monitor import rebuild_supplier_mappings, refresh_supplier_prices


def run_pricing_watch(*, max_supplier_items: int = 500, live: bool = True) -> dict[str, Any]:
    """Read-only marketplace watch. Never changes a remote sale price."""
    mapping = rebuild_supplier_mappings()
    supplier = refresh_supplier_prices(max_items=max(1, int(max_supplier_items)))
    rows = load_price_rows(live=bool(live))
    policy = get_policy()
    queue = sync_approval_queue(rows, policy.target_margin_rate)

    critical = [x for x in queue["notify_items"] if x["level"] == "CRITICAL"]
    high = [x for x in queue["notify_items"] if x["level"] == "HIGH"]
    warning = [x for x in queue["notify_items"] if x["level"] == "WARNING"]

    should_notify = bool(queue["created"] or queue["escalated"])
    notified = False
    if should_notify:
        lines = []
        for item in queue["notify_items"][:8]:
            lines.append(f"• [{item['level']}] {item['name'][:35]} — {item['reason']}")
        level = NotifyLevel.CRITICAL if critical else NotifyLevel.WARNING
        notified = notify(
            level=level,
            title=f"판매가·마진 승인대기 {queue['pending']}건",
            body=(
                f"신규 {queue['created']} / 위험상승 {queue['escalated']} / 자동해소 {queue['resolved']}\n"
                f"CRITICAL {len(critical)} / HIGH {len(high)} / WARNING {len(warning)}\n\n"
                + "\n".join(lines)
                + "\n\n※ 자동 가격변경은 실행하지 않았습니다. 판매가·마진 최적화 화면에서 검토 후 승인하세요."
            ),
            event_type=EventType.PRICE_MARGIN_ALERT,
        )

    return {
        "ok": True,
        "remote_price_mutations": 0,
        "mapping": mapping,
        "supplier_refresh": supplier,
        "market_rows": len(rows),
        "approval_queue": queue,
        "notification_sent": bool(notified),
    }
