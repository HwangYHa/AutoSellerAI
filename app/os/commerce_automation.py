"""Full commerce automation orchestration.

Claims, inquiries, settlements, inventory sold-out/restock and scheduler rules share
one persistent Seller OS state. External mutations always pass the idempotent
operation journal; AI inquiry text is draft-only until an operator sends it.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.db import get_db
from app.os.approvals import execute_idempotent
from app.os.commerce_automation_models import (
    OSChannelSettlement,
    OSInquiryTemplate,
    OSInventoryAutomationState,
    OSMarketplaceInquiry,
    OSSchedulerRule,
)
from app.os.commerce_ops import ingest_claims
from app.os.commerce_ops_models import OSChannelTemplate, OSInventoryPolicy
from app.os.models import (
    OSFulfillment,
    OSListing,
    OSProduct,
    OSSalesOrder,
    OSSalesOrderItem,
    OSSettlementLine,
    OSSupplierOffer,
)
from app.os.schema import ensure_os_schema
from app.platforms.commerce_ops_api import (
    answer_coupang_inquiry,
    answer_naver_product_inquiry,
    change_naver_sale_status,
    collect_coupang_claims,
    collect_coupang_inquiries,
    collect_coupang_settlements,
    collect_naver_claims,
    collect_naver_inquiries,
    collect_naver_settlements,
    set_coupang_listing_stock,
)
from app.platforms.naver_customer_inquiries import (
    answer_naver_customer_inquiry,
    collect_naver_customer_inquiries,
)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str, default: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else default
    except Exception:
        return default


def sync_claims(hours_back: int = 24) -> dict[str, Any]:
    """Collect real cancel/return/exchange changes from both marketplaces."""
    result: dict[str, Any] = {"coupang": {}, "smartstore": {}, "errors": []}
    all_claims: list[dict[str, Any]] = []
    for platform, collector in (("coupang", collect_coupang_claims), ("smartstore", collect_naver_claims)):
        try:
            rows = collector(hours_back=hours_back)
            all_claims.extend(rows)
            result[platform] = {"collected": len(rows)}
        except Exception as exc:
            result[platform] = {"collected": 0, "error": f"{type(exc).__name__}: {exc}"}
            result["errors"].append(f"{platform}: {exc}")
    ingested = ingest_claims(all_claims) if all_claims else {
        "ok": True, "inserted": 0, "updated": 0, "blocked_order_items": 0,
    }
    result["ingested"] = ingested
    return result


def _upsert_inquiry(row: dict[str, Any]) -> tuple[bool, int]:
    platform = str(row.get("platform") or "").lower()
    inquiry_type = str(row.get("inquiry_type") or "product")
    external_id = str(row.get("external_inquiry_id") or "")
    if not platform or not external_id:
        return False, 0
    with get_db() as db:
        record = db.query(OSMarketplaceInquiry).filter_by(
            platform=platform,
            inquiry_type=inquiry_type,
            external_inquiry_id=external_id,
        ).first()
        created = record is None
        if not record:
            record = OSMarketplaceInquiry(
                platform=platform,
                inquiry_type=inquiry_type,
                external_inquiry_id=external_id,
            )
            db.add(record)
        record.external_order_id = str(row.get("external_order_id") or "")
        record.external_item_id = str(row.get("external_item_id") or "")
        record.title = str(row.get("title") or "")[:500]
        record.question = str(row.get("question") or "")
        record.customer_name = str(row.get("customer_name") or "")[:120]
        record.category = str(row.get("category") or "")[:80]
        if str(row.get("status") or "") == "answered":
            record.status = "answered"
            record.answer = str(row.get("answer") or "")
            record.requires_human = False
        elif record.status != "answered":
            record.status = "open"
            record.requires_human = True
        record.raw_json = _dump(row.get("raw") or row)
        asked_at = row.get("asked_at")
        if asked_at:
            try:
                record.asked_at = datetime.fromisoformat(str(asked_at).replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass
        db.commit(); db.refresh(record)
        return created, int(record.id)


def sync_inquiries() -> dict[str, Any]:
    """Collect Coupang product inquiries and Naver product + buyer inquiries."""
    ensure_os_schema()
    stats: dict[str, Any] = {"collected": 0, "created": 0, "updated": 0, "errors": [], "sources": {}}
    collectors = (
        ("coupang_product", collect_coupang_inquiries),
        ("smartstore_product", collect_naver_inquiries),
        ("smartstore_customer", collect_naver_customer_inquiries),
    )
    for source, collector in collectors:
        try:
            rows = collector()
            stats["sources"][source] = len(rows)
            stats["collected"] += len(rows)
            for row in rows:
                created, _ = _upsert_inquiry(row)
                stats["created" if created else "updated"] += 1
        except Exception as exc:
            message = f"{source}: {type(exc).__name__}: {exc}"
            stats["errors"].append(message)
            stats["sources"][source] = {"error": message}
    return stats


def save_inquiry_template(*, key: str, name: str, body: str, platform: str = "all", category: str = "") -> dict[str, Any]:
    ensure_os_schema(); key = str(key).strip(); platform = str(platform or "all").lower()
    if not key or not name or not body:
        return {"ok": False, "error": "템플릿 키/이름/본문이 필요합니다."}
    with get_db() as db:
        row = db.query(OSInquiryTemplate).filter_by(platform=platform, key=key).first()
        if not row:
            row = OSInquiryTemplate(platform=platform, key=key, name=str(name)[:160])
            db.add(row)
        row.name = str(name)[:160]
        row.body = str(body)
        row.category = str(category)[:80]
        row.enabled = True
        db.commit(); db.refresh(row)
        return {"ok": True, "template_id": row.id}


def generate_ai_inquiry_draft(inquiry_id: int) -> dict[str, Any]:
    """Generate a grounded draft only. It is never posted automatically."""
    ensure_os_schema()
    with get_db() as db:
        row = db.query(OSMarketplaceInquiry).filter_by(id=int(inquiry_id)).first()
        if not row:
            return {"ok": False, "error": "문의가 없습니다."}
        product = db.query(OSProduct).filter_by(id=row.product_id).first() if row.product_id else None
        templates = db.query(OSInquiryTemplate).filter(OSInquiryTemplate.enabled.is_(True)).all()
        template_text = "\n".join(f"[{x.key}] {x.body}" for x in templates[:20])
        product_facts = {
            "name": product.name if product else "",
            "brand": product.brand if product else "",
            "category": product.category if product else "",
            "origin": product.origin if product else "",
            "material": product.material if product else "",
        }
        question = row.question
        inquiry_category = row.category

    from app.config import get_settings
    settings = get_settings()
    if not settings.claude_api_key:
        draft = "안녕하세요. 문의 주셔서 감사합니다. 확인이 필요한 내용은 판매자 확인 후 정확히 안내드리겠습니다."
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.claude_api_key)
        prompt = f"""당신은 한국 온라인쇼핑몰 판매자 CS 담당자입니다.
절대로 제공되지 않은 상품 사양, 배송일, 재고, 인증, 효능, 환불 가능 여부를 만들어내지 마세요.
배송/취소/반품/교환/환불 문의에서 실제 주문 상태가 제공되지 않았다면 확인 후 안내한다고 답하세요.
개인정보를 답변에 반복하지 마세요. 판매자에게 불리한 법적 약속을 임의 생성하지 마세요.

문의 유형: {inquiry_category}
상품 사실: {json.dumps(product_facts, ensure_ascii=False)}
사용 가능한 답변 템플릿:\n{template_text or '(없음)'}
고객 문의: {question}

정중하고 짧은 한국어 답변 초안만 작성하세요."""
        msg = client.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        draft = "".join(getattr(x, "text", "") for x in msg.content).strip()
    with get_db() as db:
        row = db.query(OSMarketplaceInquiry).filter_by(id=int(inquiry_id)).first()
        if row:
            row.ai_draft = draft
            row.status = "drafted" if row.status != "answered" else row.status
            db.commit()
    return {"ok": True, "draft": draft}


def answer_inquiry(inquiry_id: int, answer: str, *, actor: str = "seller") -> dict[str, Any]:
    """Post an operator-approved inquiry answer idempotently."""
    ensure_os_schema(); answer = str(answer or "").strip()
    if not answer:
        return {"ok": False, "error": "답변이 비어 있습니다."}
    with get_db() as db:
        row = db.query(OSMarketplaceInquiry).filter_by(id=int(inquiry_id)).first()
        if not row:
            return {"ok": False, "error": "문의가 없습니다."}
        platform = row.platform
        external_id = row.external_inquiry_id
        inquiry_type = row.inquiry_type
        raw = _loads(row.raw_json, {})
        answer_content_id = str(raw.get("answerContentId") or "") if isinstance(raw, dict) else ""

    def executor() -> dict[str, Any]:
        if platform == "coupang" and inquiry_type == "product":
            result = answer_coupang_inquiry(external_id, answer)
        elif platform == "smartstore" and inquiry_type == "product":
            result = answer_naver_product_inquiry(external_id, answer)
        elif platform == "smartstore" and inquiry_type == "customer":
            result = answer_naver_customer_inquiry(external_id, answer, answer_content_id=answer_content_id)
        else:
            raise RuntimeError(f"현재 자동답변 전송을 지원하지 않는 문의 유형입니다: {platform}/{inquiry_type}")
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "문의 답변 전송 실패")
        return result

    result = execute_idempotent(
        action_type="marketplace.inquiry.answer",
        entity_type="inquiry",
        entity_id=str(inquiry_id),
        payload={"answer": answer},
        executor=executor,
        require_approval=False,
        actor=actor,
    )
    if result.get("ok"):
        with get_db() as db:
            row = db.query(OSMarketplaceInquiry).filter_by(id=int(inquiry_id)).first()
            if row:
                row.answer = answer
                row.status = "answered"
                row.requires_human = False
                row.answered_at = datetime.utcnow()
                db.commit()
    return result


def _upsert_settlement(row: dict[str, Any]) -> bool:
    with get_db() as db:
        current = db.query(OSChannelSettlement).filter_by(
            platform=row["platform"], external_key=row["external_key"]
        ).first()
        created = current is None
        if not current:
            current = OSChannelSettlement(platform=row["platform"], external_key=row["external_key"])
            db.add(current)
        for field in (
            "external_order_id", "external_item_id", "settlement_type",
            "recognition_date", "settlement_date", "gross_revenue_krw",
            "platform_fee_krw", "shipping_amount_krw", "settlement_amount_krw", "quantity",
        ):
            setattr(current, field, row.get(field) or (0 if field.endswith("_krw") or field == "quantity" else ""))
        current.raw_json = _dump(row.get("raw") or row)
        db.commit()
        return created


def reconcile_channel_settlements() -> dict[str, int]:
    """Promote marketplace settlement facts into the canonical order-item P&L ledger."""
    ensure_os_schema()
    stats = {"matched": 0, "created": 0, "updated": 0, "unmatched": 0}
    with get_db() as db:
        channels = db.query(OSChannelSettlement).all()
        for ch in channels:
            if not ch.external_order_id:
                stats["unmatched"] += 1
                continue
            order = db.query(OSSalesOrder).filter_by(
                platform=ch.platform,
                external_order_id=ch.external_order_id,
            ).first()
            if not order:
                stats["unmatched"] += 1
                continue
            item_q = db.query(OSSalesOrderItem).filter_by(order_id=order.id)
            item = item_q.filter_by(external_item_id=ch.external_item_id).first() if ch.external_item_id else None
            if not item and item_q.count() == 1:
                item = item_q.first()
            if not item:
                stats["unmatched"] += 1
                continue
            line = db.query(OSSettlementLine).filter_by(order_item_id=item.id).first()
            created = line is None
            if not line:
                line = OSSettlementLine(order_item_id=item.id, platform=ch.platform)
                db.add(line)
            fulfillment = db.query(OSFulfillment).filter_by(order_item_id=item.id).first()
            line.gross_revenue_krw = int(ch.gross_revenue_krw or line.gross_revenue_krw or 0)
            line.platform_fee_krw = int(ch.platform_fee_krw or 0)
            if fulfillment:
                line.supply_cost_krw = int(fulfillment.supply_cost_krw or line.supply_cost_krw or 0)
                line.shipping_cost_krw = int(fulfillment.shipping_cost_krw or line.shipping_cost_krw or 0)
            revenue = int(line.gross_revenue_krw or 0)
            costs = (
                int(line.supply_cost_krw or 0) + int(line.platform_fee_krw or 0)
                + int(line.shipping_cost_krw or 0) + int(line.ad_cost_krw or 0)
                + int(line.return_cost_krw or 0) + int(line.tax_cost_krw or 0)
            )
            line.net_profit_krw = revenue - costs
            line.status = "settled" if ch.settlement_date else "provisional"
            if ch.settlement_date:
                try:
                    line.settled_at = datetime.fromisoformat(ch.settlement_date[:10])
                except Exception:
                    line.settled_at = line.settled_at or datetime.utcnow()
            stats["matched"] += 1
            stats["created" if created else "updated"] += 1
        db.commit()
    return stats


def sync_settlements(days: int = 7) -> dict[str, Any]:
    ensure_os_schema()
    stats: dict[str, Any] = {"collected": 0, "created": 0, "updated": 0, "errors": []}
    for platform, collector in (("coupang", collect_coupang_settlements), ("smartstore", collect_naver_settlements)):
        try:
            rows = collector(days=days)
            stats["collected"] += len(rows)
            for row in rows:
                stats["created" if _upsert_settlement(row) else "updated"] += 1
        except Exception as exc:
            stats["errors"].append(f"{platform}: {type(exc).__name__}: {exc}")
    stats["ledger"] = reconcile_channel_settlements()
    return stats


def apply_channel_template(product: dict[str, Any], platform: str) -> dict[str, Any]:
    """Merge a reusable channel template into a listing payload.

    Product facts win over template values. Channel-operational defaults such as
    shipping/return fees should therefore be omitted from the base product payload
    and supplied here, while facts like name/origin/category are never overwritten.
    """
    ensure_os_schema(); platform = str(platform).lower(); output = dict(product)
    with get_db() as db:
        rows = db.query(OSChannelTemplate).filter_by(platform=platform, enabled=True).order_by(OSChannelTemplate.id.asc()).all()
        if not rows:
            return output
        category = str(product.get("category") or "")
        chosen = next((x for x in rows if x.category_hint and x.category_hint in category), rows[0])
        values = _loads(chosen.template_json, {})
        if isinstance(values, dict):
            merged = dict(values)
            merged.update({k: v for k, v in output.items() if v not in (None, "")})
            output = merged
        if not output.get("category") and chosen.category_hint:
            output["category"] = chosen.category_hint
        output["channel_template_id"] = chosen.id
        output["channel_template_name"] = chosen.name
    return output


def _observed_stock(product_id: int) -> int | None:
    with get_db() as db:
        stocks = [
            x.stock_qty
            for x in db.query(OSSupplierOffer).filter_by(product_id=int(product_id), status="active").all()
            if x.stock_qty is not None
        ]
    return max(int(x) for x in stocks) if stocks else None


def run_inventory_automation(confirmations_required: int = 2) -> dict[str, Any]:
    """Auto sold-out/restock with hysteresis and ownership tracking.

    Unknown stock never triggers an external mutation. A listing is auto-restored
    only when this automation previously sold it out itself.
    """
    ensure_os_schema()
    confirmations_required = max(2, int(confirmations_required))
    result: dict[str, Any] = {"checked": 0, "sold_out": 0, "restored": 0, "skipped": 0, "errors": []}
    with get_db() as db:
        product_ids = [x.product_id for x in db.query(OSInventoryPolicy).filter_by(auto_soldout=True, sellable=True).all()]
    for product_id in product_ids:
        stock = _observed_stock(product_id)
        result["checked"] += 1
        with get_db() as db:
            policy = db.query(OSInventoryPolicy).filter_by(product_id=product_id).first()
            state = db.query(OSInventoryAutomationState).filter_by(product_id=product_id).first()
            if not state:
                state = OSInventoryAutomationState(product_id=product_id)
                db.add(state)
            state.last_observed_stock = stock
            state.last_checked_at = datetime.utcnow()
            if stock is None:
                state.low_stock_confirmations = 0
                state.restock_confirmations = 0
                db.commit(); result["skipped"] += 1
                continue
            threshold = int(policy.safety_stock or 0) + int(policy.reserved_qty or 0)
            if stock <= threshold:
                state.low_stock_confirmations += 1
                state.restock_confirmations = 0
            else:
                state.restock_confirmations += 1
                state.low_stock_confirmations = 0
            should_soldout = not state.auto_sold_out and state.low_stock_confirmations >= confirmations_required
            should_restore = state.auto_sold_out and state.restock_confirmations >= confirmations_required
            db.commit()
        if not (should_soldout or should_restore):
            continue
        target_qty = 0 if should_soldout else max(1, stock - int(policy.reserved_qty or 0))
        with get_db() as db:
            listings = db.query(OSListing).filter_by(product_id=product_id).filter(
                OSListing.status.in_(["active", "paused"])
            ).all()
            listing_rows = [
                (x.id, x.platform, x.external_product_id)
                for x in listings
                if x.external_product_id and not x.external_product_id.startswith("__pending__:")
            ]
        action_ok = True
        errors: list[str] = []
        for listing_id, platform, external_id in listing_rows:
            try:
                def mutate() -> dict[str, Any]:
                    if platform == "coupang":
                        return set_coupang_listing_stock(external_id, target_qty)
                    if platform == "smartstore":
                        return change_naver_sale_status(external_id, "SUSPENSION" if should_soldout else "SALE")
                    raise RuntimeError(f"지원하지 않는 판매채널: {platform}")
                op = execute_idempotent(
                    action_type="marketplace.inventory.soldout" if should_soldout else "marketplace.inventory.restore",
                    entity_type="listing",
                    entity_id=str(listing_id),
                    payload={"qty": target_qty, "observed_stock": stock, "confirmations": confirmations_required},
                    executor=mutate,
                    require_approval=False,
                    actor="inventory-automation",
                )
                if not op.get("ok"):
                    action_ok = False
                    errors.append(f"listing {listing_id}: {op.get('error')}")
            except Exception as exc:
                action_ok = False
                errors.append(f"listing {listing_id}: {type(exc).__name__}: {exc}")
        result["errors"].extend(errors)
        with get_db() as db:
            state = db.query(OSInventoryAutomationState).filter_by(product_id=product_id).first()
            if state and errors:
                state.last_error = " | ".join(errors)[:2000]
                db.commit()
        if listing_rows and action_ok:
            with get_db() as db:
                state = db.query(OSInventoryAutomationState).filter_by(product_id=product_id).first()
                state.auto_sold_out = should_soldout
                state.last_action = "sold_out" if should_soldout else "restored"
                state.last_action_at = datetime.utcnow()
                state.last_error = ""
                for listing_id, _, _ in listing_rows:
                    listing = db.query(OSListing).filter_by(id=listing_id).first()
                    if listing:
                        listing.status = "paused" if should_soldout else "active"
                db.commit()
            result["sold_out" if should_soldout else "restored"] += 1
    return result


def save_scheduler_rule(
    task_type: str,
    interval_minutes: int,
    *,
    enabled: bool = True,
    queue_name: str = "sync",
    payload: dict[str, Any] | None = None,
    description: str = "",
) -> dict[str, Any]:
    ensure_os_schema(); interval = max(1, int(interval_minutes))
    allowed = {
        "order_sync", "claim_sync", "payment_sync", "fulfillment_cycle", "inquiry_sync",
        "inventory_automation", "settlement_sync", "catalog_sync", "data_reconcile",
    }
    if task_type not in allowed:
        return {"ok": False, "error": f"GUI 스케줄에서 허용되지 않는 작업입니다: {task_type}"}
    with get_db() as db:
        row = db.query(OSSchedulerRule).filter_by(task_type=task_type).first()
        if not row:
            row = OSSchedulerRule(task_type=task_type)
            db.add(row)
        row.enabled = bool(enabled)
        row.interval_minutes = interval
        row.queue_name = str(queue_name or "sync")[:40]
        row.payload_json = _dump(payload or {})
        row.description = str(description)[:400]
        db.commit(); db.refresh(row)
        return {"ok": True, "rule_id": row.id}


def get_automation_dashboard() -> dict[str, Any]:
    ensure_os_schema()
    with get_db() as db:
        inquiries = db.query(OSMarketplaceInquiry).order_by(
            OSMarketplaceInquiry.asked_at.desc(), OSMarketplaceInquiry.id.desc()
        ).limit(300).all()
        templates = db.query(OSInquiryTemplate).filter_by(enabled=True).order_by(OSInquiryTemplate.platform, OSInquiryTemplate.key).all()
        settlements = db.query(OSChannelSettlement).order_by(
            OSChannelSettlement.recognition_date.desc(), OSChannelSettlement.id.desc()
        ).limit(500).all()
        rules = db.query(OSSchedulerRule).order_by(OSSchedulerRule.task_type).all()
        inv = db.query(OSInventoryAutomationState).order_by(OSInventoryAutomationState.updated_at.desc()).limit(300).all()
        return {
            "inquiries": [
                {"id": x.id, "platform": x.platform, "type": x.inquiry_type, "category": x.category,
                 "title": x.title, "question": x.question, "customer": x.customer_name,
                 "status": x.status, "answer": x.answer, "ai_draft": x.ai_draft,
                 "asked_at": x.asked_at, "requires_human": x.requires_human}
                for x in inquiries
            ],
            "inquiry_templates": [
                {"id": x.id, "platform": x.platform, "key": x.key, "name": x.name,
                 "category": x.category, "body": x.body}
                for x in templates
            ],
            "settlements": [
                {"id": x.id, "platform": x.platform, "order_id": x.external_order_id,
                 "item_id": x.external_item_id, "type": x.settlement_type,
                 "recognition_date": x.recognition_date, "settlement_date": x.settlement_date,
                 "revenue": x.gross_revenue_krw, "fee": x.platform_fee_krw,
                 "settlement": x.settlement_amount_krw}
                for x in settlements
            ],
            "scheduler_rules": [
                {"id": x.id, "task_type": x.task_type, "enabled": x.enabled,
                 "interval_minutes": x.interval_minutes, "queue": x.queue_name,
                 "payload": _loads(x.payload_json, {}), "description": x.description}
                for x in rules
            ],
            "inventory_states": [
                {"product_id": x.product_id, "stock": x.last_observed_stock,
                 "low_confirms": x.low_stock_confirmations, "restock_confirms": x.restock_confirmations,
                 "auto_sold_out": x.auto_sold_out, "last_action": x.last_action,
                 "last_error": x.last_error, "last_checked_at": x.last_checked_at}
                for x in inv
            ],
        }
