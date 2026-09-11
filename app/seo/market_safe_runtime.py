"""Lock-safe persistence for the marketplace SEO workflow.

The legacy optimizer performs read-then-write transactions. Under WAL a read
transaction can still fail when it later upgrades to a writer after another
process committed. Every operation here creates a fresh Session on every retry.
Remote marketplace mutations are executed exactly once; only local SQLite writes
are retried.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from sqlalchemy.exc import OperationalError

from app.db import get_db
from app.seo.market_models import MarketSeoApplyLog, MarketSeoAudit, ensure_market_seo_schema
from app.sqlite_runtime import retry_sqlite_write


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _approve_fields(self, audit_id: int, fields: Iterable[str]) -> dict:
    from app.seo.market_optimizer import SEO_WRITE_FIELDS

    allowed = sorted(set(fields) & SEO_WRITE_FIELDS)
    if not allowed:
        return {"ok": False, "error": "승인할 수 있는 SEO 필드가 선택되지 않았습니다."}

    def write_once() -> dict:
        with get_db() as db:
            row = db.query(MarketSeoAudit).filter_by(id=int(audit_id)).first()
            if not row:
                return {"ok": False, "error": "진단 결과를 찾을 수 없습니다."}
            row.selected_fields_json = _json(allowed)
            row.status = "APPROVED"
            row.updated_at = datetime.utcnow()
            db.commit()
            return {"ok": True, "fields": allowed}

    try:
        return retry_sqlite_write(write_once, attempts=8)
    except OperationalError as exc:
        return {"ok": False, "error": f"SEO 승인 저장 중 DB가 계속 사용 중입니다: {exc}"}


def _persist(self, audit, error: str = "") -> None:
    data = audit.as_dict()

    def write_once() -> int:
        with get_db() as db:
            row = MarketSeoAudit(
                batch_id=audit.batch_id,
                product_id=audit.product_id,
                listing_id=audit.listing_id,
                platform=audit.platform,
                platform_product_id=audit.platform_product_id,
                product_name=audit.product_name,
                quality_score=audit.quality_score,
                proposed_score=audit.proposed_score,
                opportunity_score=audit.opportunity_score,
                priority_grade=audit.priority_grade,
                classification=audit.classification,
                issue_count=data["issue_count"],
                critical_count=data["critical_count"],
                warning_count=data["warning_count"],
                recent_orders=audit.recent_orders,
                sales_protected=audit.sales_protected,
                current_json=_json(audit.current),
                proposed_json=_json(audit.proposed),
                issues_json=_json(data["issues"]),
                evidence_json=_json(audit.evidence),
                data_sources_json=_json(audit.data_sources),
                limitations_json=_json(audit.limitations),
                error=error,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)

    audit.audit_id = retry_sqlite_write(write_once, attempts=8)


def _apply_audit(self, audit_id: int, fields: Iterable[str] | None = None, *, confirm_sales_protected: bool = False) -> dict:
    from app.seo.market_optimizer import SEO_WRITE_FIELDS

    # Read-only snapshot first. No Session survives into a write transaction.
    with get_db() as db:
        row = db.query(MarketSeoAudit).filter_by(id=int(audit_id)).first()
        if not row:
            return {"ok": False, "error": "진단 결과를 찾을 수 없습니다."}
        proposed = json.loads(row.proposed_json or "{}")
        selected = set(fields or json.loads(row.selected_fields_json or "[]")) & SEO_WRITE_FIELDS
        sales_protected = bool(row.sales_protected)
        platform = str(row.platform)
        platform_id = str(row.platform_product_id)
        audit_snapshot = {
            "audit_id": int(row.id),
            "product_id": int(row.product_id),
            "listing_id": int(row.listing_id),
            "platform": platform,
            "platform_product_id": platform_id,
        }

    if sales_protected and "title" in selected and not confirm_sales_protected:
        return {"ok": False, "error": "최근 판매이력이 있는 상품입니다. 제목 변경은 판매이력 보호 확인이 필요합니다."}
    if not selected:
        return {"ok": False, "error": "사용자가 승인한 자동 반영 필드가 없습니다."}

    selected_sorted = sorted(selected)

    def create_log_once() -> int:
        with get_db() as db:
            log = MarketSeoApplyLog(
                audit_id=audit_snapshot["audit_id"],
                product_id=audit_snapshot["product_id"],
                listing_id=audit_snapshot["listing_id"],
                platform=audit_snapshot["platform"],
                platform_product_id=audit_snapshot["platform_product_id"],
                selected_fields_json=_json(selected_sorted),
                status="RUNNING",
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return int(log.id)

    try:
        log_id = retry_sqlite_write(create_log_once, attempts=8)
    except OperationalError as exc:
        return {"ok": False, "error": f"적용 기록 생성 중 DB가 계속 사용 중입니다: {exc}", "audit_id": audit_id, "fields": selected_sorted}

    # IMPORTANT: remote marketplace mutation is called exactly once.
    if platform == "coupang":
        result = self.coupang.apply_fields(platform_id, proposed, selected)
    else:
        result = self.naver.apply_fields(platform_id, proposed, selected)

    def finish_log_once() -> None:
        with get_db() as db:
            log = db.query(MarketSeoApplyLog).filter_by(id=log_id).first()
            row = db.query(MarketSeoAudit).filter_by(id=int(audit_id)).first()
            now = datetime.utcnow()
            if log:
                log.before_json = _json(result.get("before") or {})
                log.after_json = _json(result.get("after") or {})
                log.finished_at = now
                log.status = "APPLIED" if result.get("ok") else "APPLY_FAILED"
                log.error = str(result.get("error") or "")
            if row:
                row.selected_fields_json = _json(selected_sorted)
                row.applied_at = now if result.get("ok") else None
                row.status = "APPLIED" if result.get("ok") else "APPLY_FAILED"
                row.error = str(result.get("error") or "")
                row.updated_at = now
            db.commit()

    try:
        retry_sqlite_write(finish_log_once, attempts=8)
    except OperationalError as exc:
        # Do not ask the user to retry the remote mutation. It may already have
        # succeeded; surface a local-log warning while preserving the API result.
        return {
            **result,
            "audit_id": audit_id,
            "fields": selected_sorted,
            "local_log_warning": f"마켓 반영 후 로컬 결과 기록이 DB 잠금으로 지연되었습니다: {exc}",
        }

    return {**result, "audit_id": audit_id, "fields": selected_sorted}


def _apply_many(self, selections: dict[int, Iterable[str]], *, confirm_sales_protected: bool = False) -> dict:
    results: list[dict] = []
    for audit_id, fields in selections.items():
        try:
            result = self.apply_audit(int(audit_id), fields, confirm_sales_protected=confirm_sales_protected)
        except Exception as exc:  # isolate one product from the rest of a bulk run
            result = {"ok": False, "audit_id": int(audit_id), "error": str(exc)}
        results.append(result)
    return {
        "ok": all(x.get("ok") for x in results) if results else False,
        "total": len(results),
        "success": sum(1 for x in results if x.get("ok")),
        "failed": sum(1 for x in results if not x.get("ok")),
        "results": results,
    }


def install_market_seo_safe_writes() -> None:
    """Patch MarketSeoOptimizer's local persistence methods once per process."""
    ensure_market_seo_schema()
    from app.seo.market_optimizer import MarketSeoOptimizer

    if getattr(MarketSeoOptimizer, "_sqlite_safe_writes_installed", False):
        return
    MarketSeoOptimizer._persist = _persist
    MarketSeoOptimizer.approve_fields = _approve_fields
    MarketSeoOptimizer.apply_audit = _apply_audit
    MarketSeoOptimizer.apply_many = _apply_many
    MarketSeoOptimizer._sqlite_safe_writes_installed = True


__all__ = ["install_market_seo_safe_writes"]
