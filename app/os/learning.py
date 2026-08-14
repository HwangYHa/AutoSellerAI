"""Build AI-learning facts from settled operational outcomes.

This layer does not train a model by itself. It converts actual settled profit and
return outcomes into stable, auditable signals that recommendation models can use.
"""
from __future__ import annotations

import json
from datetime import datetime

from app.db import get_db
from app.os.models import OSLearningSignal, OSSalesOrderItem, OSSettlementLine
from app.os.schema import ensure_os_schema


def _context(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _upsert_signal(db, *, item: OSSalesOrderItem, line: OSSettlementLine, signal_type: str, value_int: int) -> bool:
    context_json = _context({"settlement_line_id": line.id, "order_item_id": item.id})
    row = db.query(OSLearningSignal).filter_by(
        product_id=item.product_id,
        variant_id=item.variant_id,
        listing_id=item.listing_id,
        signal_type=signal_type,
        context_json=context_json,
    ).first()
    observed_at = line.settled_at or line.updated_at or datetime.utcnow()
    if row:
        changed = row.value_int != int(value_int) or row.observed_at != observed_at
        row.value_int = int(value_int)
        row.observed_at = observed_at
        return changed
    db.add(OSLearningSignal(
        product_id=item.product_id,
        variant_id=item.variant_id,
        listing_id=item.listing_id,
        signal_type=signal_type,
        value_int=int(value_int),
        context_json=context_json,
        observed_at=observed_at,
    ))
    return True


def refresh_profit_learning_signals() -> dict:
    """Translate settlement lines into product/variant/listing outcome signals."""
    ensure_os_schema()
    created_or_updated = 0
    skipped = 0
    with get_db() as db:
        lines = db.query(OSSettlementLine).all()
        for line in lines:
            item = db.query(OSSalesOrderItem).filter_by(id=line.order_item_id).first()
            if not item or not item.product_id:
                skipped += 1
                continue
            revenue = int(line.gross_revenue_krw or 0)
            profit = int(line.net_profit_krw or 0)
            margin_bps = int(round((profit / revenue) * 10000)) if revenue else 0
            signals = {
                "net_profit_krw": profit,
                "margin_bps": margin_bps,
                "return_cost_krw": int(line.return_cost_krw or 0),
                "platform_fee_krw": int(line.platform_fee_krw or 0),
            }
            for signal_type, value in signals.items():
                created_or_updated += int(_upsert_signal(
                    db,
                    item=item,
                    line=line,
                    signal_type=signal_type,
                    value_int=value,
                ))
        db.commit()
    return {
        "ok": True,
        "settlement_lines": len(lines),
        "signals_changed": created_or_updated,
        "skipped_unlinked": skipped,
    }
