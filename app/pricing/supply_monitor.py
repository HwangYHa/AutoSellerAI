from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import desc

from app.db import Listing, Product, SupplierRawProduct, SupplierWorkflowItem, get_db
from app.pricing.models import (
    PriceRiskSnapshot,
    SupplierProductMap,
    SupplyPriceSnapshot,
    ensure_pricing_schema,
)
from app.seo.duplicate_detector import _normalize
from app.sqlite_runtime import retry_sqlite_write, sqlite_writer_guard
from app.suppliers.registry import get_adapter


KNOWN_SUPPLIERS = {"domeggook", "domemai", "onchannel", "ownerclan"}
DEFAULT_MAX_SUPPLY_AGE_HOURS = 72.0

_SUPPLIER_ALIASES = {
    "domeggook": "domeggook",
    "도매꾹": "domeggook",
    "domemai": "domemai",
    "도매매": "domemai",
    "onchannel": "onchannel",
    "onchanel": "onchannel",
    "온채널": "onchannel",
    "ownerclan": "ownerclan",
    "owner_clan": "ownerclan",
    "오너클랜": "ownerclan",
}


def _supplier_from_url(url: str) -> str:
    try:
        host = urlparse(str(url or "")).netloc.lower()
    except Exception:
        return ""
    if "domeggook" in host:
        return "domeggook"
    if "domeme" in host or "domemai" in host:
        return "domemai"
    if "onch3" in host or "onchannel" in host:
        return "onchannel"
    if "ownerclan" in host:
        return "ownerclan"
    return ""


def _raw_id_from_supplier_url(supplier_id: str, url: str) -> str:
    try:
        parsed = urlparse(str(url or ""))
        query = parse_qs(parsed.query)
    except Exception:
        return ""
    keys_by_supplier = {
        "domeggook": ("itemNo", "itemno", "no"),
        "domemai": ("itemNo", "itemno", "no"),
        "onchannel": ("pcode", "productCode", "product_code", "idx", "no"),
        "ownerclan": ("itemCode", "itemcode", "key"),
    }
    for key in keys_by_supplier.get(supplier_id, ()):
        values = query.get(key)
        if values and str(values[0]).strip():
            return str(values[0]).strip()
    return ""


@dataclass
class MappingCandidate:
    product_id: int
    supplier_id: str
    raw_id: str
    match_type: str
    confidence: float
    verified: bool
    supply_price: float


def _utcnow() -> datetime:
    return datetime.utcnow()


def _safe_supplier_source(source: str) -> str:
    value = str(source or "").strip().lower()
    return _SUPPLIER_ALIASES.get(value, value if value in KNOWN_SUPPLIERS else "")


def _mapping_candidate_for_product(db, product: Product) -> MappingCandidate | None:
    direct_supplier = _safe_supplier_source(product.source)
    if direct_supplier and str(product.source_id or "").strip():
        return MappingCandidate(
            product_id=product.id,
            supplier_id=direct_supplier,
            raw_id=str(product.source_id).strip(),
            match_type="direct_source",
            confidence=1.0,
            verified=True,
            supply_price=float(product.supply_price or 0),
        )

    raw = (
        db.query(SupplierRawProduct)
        .filter(SupplierRawProduct.product_id == product.id)
        .order_by(desc(SupplierRawProduct.updated_at))
        .first()
    )
    if raw and _safe_supplier_source(raw.supplier_id) and str(raw.raw_id or "").strip():
        return MappingCandidate(
            product_id=product.id,
            supplier_id=str(raw.supplier_id).strip().lower(),
            raw_id=str(raw.raw_id).strip(),
            match_type="supplier_raw_link",
            confidence=1.0,
            verified=True,
            supply_price=float(raw.raw_price or 0),
        )

    workflow = (
        db.query(SupplierWorkflowItem)
        .filter(SupplierWorkflowItem.product_id == product.id)
        .order_by(desc(SupplierWorkflowItem.updated_at))
        .first()
    )
    if workflow and _safe_supplier_source(workflow.supplier_id) and str(workflow.raw_id or "").strip():
        return MappingCandidate(
            product_id=product.id,
            supplier_id=_safe_supplier_source(workflow.supplier_id),
            raw_id=str(workflow.raw_id).strip(),
            match_type="supplier_workflow_link",
            confidence=0.99,
            verified=True,
            supply_price=float(workflow.supply_price or 0),
        )

    url_supplier = _supplier_from_url(product.source_url)
    url_raw_id = _raw_id_from_supplier_url(url_supplier, product.source_url) if url_supplier else ""
    if url_supplier and url_raw_id:
        local_raw = (
            db.query(SupplierRawProduct)
            .filter_by(supplier_id=url_supplier, raw_id=url_raw_id)
            .order_by(desc(SupplierRawProduct.updated_at))
            .first()
        )
        return MappingCandidate(
            product_id=product.id,
            supplier_id=url_supplier,
            raw_id=url_raw_id,
            match_type="supplier_url",
            confidence=0.995,
            verified=True,
            supply_price=float((local_raw.raw_price if local_raw else 0) or product.supply_price or 0),
        )

    exact_raw = [
        row for row in db.query(SupplierRawProduct).filter(SupplierRawProduct.raw_name == product.name).all()
        if _safe_supplier_source(row.supplier_id) and str(row.raw_id or "").strip()
    ]
    exact_raw_keys = {( _safe_supplier_source(row.supplier_id), str(row.raw_id).strip()): row for row in exact_raw}
    if len(exact_raw_keys) == 1:
        (supplier_id, raw_id), row = next(iter(exact_raw_keys.items()))
        return MappingCandidate(
            product_id=product.id,
            supplier_id=supplier_id,
            raw_id=raw_id,
            match_type="supplier_raw_exact_name_unique",
            confidence=0.98,
            verified=False,
            supply_price=float(row.raw_price or 0),
        )

    exact_workflow = [
        row for row in db.query(SupplierWorkflowItem).filter(SupplierWorkflowItem.product_name == product.name).all()
        if _safe_supplier_source(row.supplier_id) and str(row.raw_id or "").strip()
    ]
    exact_workflow_keys = {( _safe_supplier_source(row.supplier_id), str(row.raw_id).strip()): row for row in exact_workflow}
    if len(exact_workflow_keys) == 1:
        (supplier_id, raw_id), row = next(iter(exact_workflow_keys.items()))
        return MappingCandidate(
            product_id=product.id,
            supplier_id=supplier_id,
            raw_id=raw_id,
            match_type="supplier_workflow_exact_name_unique",
            confidence=0.97,
            verified=False,
            supply_price=float(row.supply_price or 0),
        )

    key = _normalize(product.name)
    if not key:
        return None

    candidates: list[Product] = []
    for candidate in db.query(Product).filter(Product.supply_price > 0).all():
        if candidate.id == product.id:
            continue
        supplier = _safe_supplier_source(candidate.source)
        if not supplier or not str(candidate.source_id or "").strip():
            continue
        if _normalize(candidate.name) == key:
            candidates.append(candidate)

    if len(candidates) != 1:
        return None

    candidate = candidates[0]
    return MappingCandidate(
        product_id=product.id,
        supplier_id=str(candidate.source).strip().lower(),
        raw_id=str(candidate.source_id).strip(),
        match_type="exact_name_unique",
        confidence=0.95,
        verified=False,
        supply_price=float(candidate.supply_price or 0),
    )


def rebuild_supplier_mappings() -> dict[str, Any]:
    """Create/refresh durable supplier mappings without fuzzy matching."""
    ensure_pricing_schema()
    with get_db() as db:
        product_ids = [
            row[0]
            for row in (
                db.query(Product.id)
                .join(Listing, Listing.product_id == Product.id)
                .filter(
                    Listing.status == "success",
                    Listing.platform.in_(["coupang", "smartstore"]),
                )
                .distinct()
                .all()
            )
        ]

    created = updated = matched = unmatched = preserved = 0
    by_type: dict[str, int] = {}

    for product_id in product_ids:
        with get_db() as db:
            product = db.get(Product, product_id)
            if not product:
                unmatched += 1
                continue
            candidate = _mapping_candidate_for_product(db, product)

        if candidate is None:
            unmatched += 1
            continue

        matched += 1
        by_type[candidate.match_type] = by_type.get(candidate.match_type, 0) + 1

        def _write() -> str:
            with get_db() as db:
                row = db.query(SupplierProductMap).filter_by(product_id=product_id).first()
                if row and row.verified and not candidate.verified:
                    return "preserved"
                if row is None:
                    row = SupplierProductMap(product_id=product_id)
                    action = "created"
                else:
                    action = "updated"
                row.supplier_id = candidate.supplier_id
                row.raw_id = candidate.raw_id
                row.match_type = candidate.match_type
                row.confidence = candidate.confidence
                row.verified = candidate.verified
                if candidate.supply_price > 0 and float(row.current_supply_price or 0) <= 0:
                    row.current_supply_price = candidate.supply_price
                row.last_error = ""
                db.add(row)
                db.commit()
                return action

        action = retry_sqlite_write(_write, attempts=8)
        if action == "created":
            created += 1
        elif action == "updated":
            updated += 1
        else:
            preserved += 1

    return {
        "total_listing_products": len(product_ids),
        "matched": matched,
        "unmatched": unmatched,
        "created": created,
        "updated": updated,
        "preserved": preserved,
        "by_type": by_type,
    }


def _record_refresh_failure(map_id: int, product_id: int, supplier_id: str, raw_id: str, error: str) -> None:
    def _write() -> None:
        with get_db() as db:
            row = db.get(SupplierProductMap, map_id)
            if row:
                row.last_error = str(error or "")[:1000]
                db.add(row)
            db.add(
                SupplyPriceSnapshot(
                    product_id=product_id,
                    supplier_id=supplier_id,
                    raw_id=raw_id,
                    old_price=float(row.current_supply_price or 0) if row else 0.0,
                    new_price=0.0,
                    change_rate=0.0,
                    status="failed",
                    error=str(error or "")[:1000],
                )
            )
            db.commit()
    retry_sqlite_write(_write, attempts=8)


def refresh_supplier_prices(*, max_items: int = 500) -> dict[str, Any]:
    """Refresh mapped supplier prices using the existing supplier adapters."""
    ensure_pricing_schema()
    with get_db() as db:
        mappings = [
            {
                "id": row.id,
                "product_id": row.product_id,
                "supplier_id": row.supplier_id,
                "raw_id": row.raw_id,
            }
            for row in (
                db.query(SupplierProductMap)
                .order_by(SupplierProductMap.last_refreshed_at.asc().nullsfirst(), SupplierProductMap.id.asc())
                .limit(max(1, int(max_items)))
                .all()
            )
        ]

    refreshed = changed = unchanged = failed = unavailable = 0
    errors: list[str] = []

    for mapping in mappings:
        adapter = get_adapter(mapping["supplier_id"])
        if adapter is None or not adapter.is_available():
            unavailable += 1
            msg = f'{mapping["supplier_id"]}/{mapping["raw_id"]}: 공급사 연동 비활성'
            _record_refresh_failure(
                mapping["id"], mapping["product_id"], mapping["supplier_id"], mapping["raw_id"], msg
            )
            errors.append(msg)
            continue

        try:
            item = adapter.get_product(mapping["raw_id"])
        except Exception as exc:
            item = None
            errors.append(f'{mapping["supplier_id"]}/{mapping["raw_id"]}: {exc}')

        if item is None or float(item.supply_price or 0) <= 0:
            failed += 1
            msg = f'{mapping["supplier_id"]}/{mapping["raw_id"]}: 유효한 최신 공급가를 조회하지 못했습니다.'
            _record_refresh_failure(
                mapping["id"], mapping["product_id"], mapping["supplier_id"], mapping["raw_id"], msg
            )
            errors.append(msg)
            continue

        new_price = float(item.supply_price)

        def _write_refresh() -> tuple[float, float]:
            with get_db() as db:
                row = db.get(SupplierProductMap, mapping["id"])
                product = db.get(Product, mapping["product_id"])
                if row is None or product is None:
                    raise ValueError("매핑 또는 상품이 삭제되었습니다.")

                old_price = float(row.current_supply_price or product.supply_price or 0)
                change_rate = ((new_price - old_price) / old_price) if old_price > 0 else 0.0

                row.previous_supply_price = old_price
                row.current_supply_price = new_price
                row.last_refreshed_at = _utcnow()
                row.last_error = ""

                # Canonical product supply price is refreshed from the durable supplier mapping.
                product.supply_price = new_price

                raw = (
                    db.query(SupplierRawProduct)
                    .filter_by(
                        supplier_id=mapping["supplier_id"],
                        raw_id=mapping["raw_id"],
                    )
                    .order_by(desc(SupplierRawProduct.updated_at))
                    .first()
                )
                if raw:
                    raw.raw_price = new_price
                    raw.updated_at = _utcnow()

                workflow = (
                    db.query(SupplierWorkflowItem)
                    .filter_by(
                        supplier_id=mapping["supplier_id"],
                        raw_id=mapping["raw_id"],
                    )
                    .order_by(desc(SupplierWorkflowItem.updated_at))
                    .first()
                )
                if workflow:
                    workflow.supply_price = new_price

                db.add(
                    SupplyPriceSnapshot(
                        product_id=product.id,
                        supplier_id=mapping["supplier_id"],
                        raw_id=mapping["raw_id"],
                        old_price=old_price,
                        new_price=new_price,
                        change_rate=change_rate,
                        status="changed" if abs(new_price - old_price) >= 1 else "unchanged",
                    )
                )
                db.commit()
                return old_price, change_rate

        try:
            old_price, change_rate = retry_sqlite_write(_write_refresh, attempts=8)
            refreshed += 1
            if abs(new_price - old_price) >= 1:
                changed += 1
            else:
                unchanged += 1
        except Exception as exc:
            failed += 1
            msg = f'{mapping["supplier_id"]}/{mapping["raw_id"]}: DB 반영 실패: {exc}'
            errors.append(msg)
            _record_refresh_failure(
                mapping["id"], mapping["product_id"], mapping["supplier_id"], mapping["raw_id"], msg
            )

    return {
        "total": len(mappings),
        "refreshed": refreshed,
        "changed": changed,
        "unchanged": unchanged,
        "failed": failed,
        "unavailable": unavailable,
        "errors": errors[:50],
    }


def supplier_mapping_state(product_id: int, *, max_age_hours: float = DEFAULT_MAX_SUPPLY_AGE_HOURS) -> dict[str, Any]:
    ensure_pricing_schema()
    with get_db() as db:
        row = db.query(SupplierProductMap).filter_by(product_id=product_id).first()
        if row is None:
            return {
                "mapped": False,
                "safe": False,
                "fresh": False,
                "age_hours": None,
                "match_type": "",
                "supplier_id": "",
                "raw_id": "",
                "price": 0.0,
                "source": "도매 매핑 없음",
                "last_error": "",
            }

        age_hours: float | None = None
        if row.last_refreshed_at:
            now = _utcnow()
            age_hours = max(0.0, (now - row.last_refreshed_at).total_seconds() / 3600.0)
        fresh = age_hours is not None and age_hours <= max_age_hours
        safe = bool(row.verified or row.match_type in {"exact_name_unique", "supplier_raw_exact_name_unique", "supplier_workflow_exact_name_unique"})
        return {
            "mapped": True,
            "safe": safe,
            "fresh": fresh,
            "age_hours": age_hours,
            "match_type": row.match_type,
            "supplier_id": row.supplier_id,
            "raw_id": row.raw_id,
            "price": float(row.current_supply_price or 0),
            "source": f"도매 매핑 · {row.supplier_id} · {row.match_type}",
            "last_error": row.last_error or "",
        }


def _fresh_local_raw_price(
    db,
    supplier_id: str,
    raw_id: str,
    *,
    max_age_hours: float = DEFAULT_MAX_SUPPLY_AGE_HOURS,
) -> tuple[float, datetime | None]:
    row = (
        db.query(SupplierRawProduct)
        .filter_by(supplier_id=supplier_id, raw_id=raw_id)
        .order_by(desc(SupplierRawProduct.updated_at))
        .first()
    )
    if row is None or float(row.raw_price or 0) <= 0 or not row.updated_at:
        return 0.0, None
    age_hours = max(0.0, (_utcnow() - row.updated_at).total_seconds() / 3600.0)
    if age_hours > max_age_hours:
        return 0.0, None
    return float(row.raw_price), row.updated_at


def list_unresolved_supplier_products(limit: int = 500) -> list[dict[str, Any]]:
    """Return listed products that still have no usable supplier lineage."""
    ensure_pricing_schema()
    with get_db() as db:
        rows = (
            db.query(Product)
            .join(Listing, Listing.product_id == Product.id)
            .filter(
                Listing.status == "success",
                Listing.platform.in_(["coupang", "smartstore"]),
            )
            .distinct()
            .limit(max(1, int(limit)))
            .all()
        )
        out: list[dict[str, Any]] = []
        for product in rows:
            mapping = db.query(SupplierProductMap).filter_by(product_id=product.id).first()
            if mapping and float(mapping.current_supply_price or 0) > 0:
                continue
            source_supplier = _safe_supplier_source(product.source)
            reason = "공급사 계보 없음"
            if mapping:
                reason = mapping.last_error or "매핑은 있으나 유효 도매가 없음"
            elif str(product.source or "").endswith("_import"):
                reason = "마켓 역동기화 상품 · 공급사 식별정보가 저장되지 않음"
            elif source_supplier and product.source_id:
                reason = "공급사 원본 ID는 있으나 매핑/도매가 최신화가 완료되지 않음"
            out.append({
                "product_id": product.id,
                "상품명": product.name,
                "상품SKU": product.sku,
                "상품source": product.source,
                "상품source_id": product.source_id,
                "상품source_url": product.source_url,
                "현재상품도매가": float(product.supply_price or 0),
                "원인": reason,
                "매핑공급사": mapping.supplier_id if mapping else "",
                "매핑원본ID": mapping.raw_id if mapping else "",
                "매핑오류": mapping.last_error if mapping else "",
            })
        return out


def supplier_mapping_suggestions(product_id: int, limit: int = 5) -> list[dict[str, Any]]:
    """Return human-review suggestions only; suggestions are never auto-applied."""
    ensure_pricing_schema()
    with get_db() as db:
        product = db.get(Product, int(product_id))
        if product is None:
            return []
        target = _normalize(product.name)
        if not target:
            return []
        candidates: dict[tuple[str, str], dict[str, Any]] = {}

        def consider(supplier_id: str, raw_id: str, name: str, price: float, source: str) -> None:
            sid = _safe_supplier_source(supplier_id)
            rid = str(raw_id or "").strip()
            if not sid or not rid or not name:
                return
            normalized = _normalize(name)
            if not normalized:
                return
            score = SequenceMatcher(None, target, normalized).ratio()
            key = (sid, rid)
            current = candidates.get(key)
            if current is None or score > current["유사도"]:
                candidates[key] = {
                    "공급사": sid,
                    "공급사상품ID": rid,
                    "후보상품명": name,
                    "도매가": float(price or 0),
                    "유사도": score,
                    "근거": source,
                }

        for row in db.query(SupplierRawProduct).all():
            consider(row.supplier_id, row.raw_id, row.raw_name, row.raw_price, "공급사 원본")
        for row in db.query(SupplierWorkflowItem).all():
            consider(row.supplier_id, row.raw_id, row.product_name, row.supply_price, "공급사 워크플로우")
        for row in db.query(Product).filter(Product.supply_price > 0).all():
            sid = _safe_supplier_source(row.source)
            if sid:
                consider(sid, row.source_id, row.name, row.supply_price, "기존 공급사 상품")

        ranked = sorted(candidates.values(), key=lambda x: (-x["유사도"], x["공급사"], x["공급사상품ID"]))
        for item in ranked:
            item["유사도(%)"] = round(float(item.pop("유사도")) * 100, 1)
        return ranked[:max(1, int(limit))]


def manual_map_supplier_product(
    product_id: int,
    supplier_id: str,
    raw_id: str,
    *,
    verify_live: bool = True,
) -> dict[str, Any]:
    """Persist an operator-confirmed supplier mapping and obtain the best trustworthy price."""
    ensure_pricing_schema()
    supplier_id = _safe_supplier_source(supplier_id)
    raw_id = str(raw_id or "").strip()
    if not supplier_id or not raw_id:
        return {"ok": False, "error": "유효한 공급사와 공급사 상품ID가 필요합니다."}

    live_price = 0.0
    live_name = ""
    refreshed_at: datetime | None = None
    if verify_live:
        adapter = get_adapter(supplier_id)
        if adapter is not None and adapter.is_available():
            try:
                item = adapter.get_product(raw_id)
                if item is not None and float(item.supply_price or 0) > 0:
                    live_price = float(item.supply_price)
                    live_name = str(item.name or "")
                    refreshed_at = _utcnow()
            except Exception:
                pass

    with get_db() as db:
        product = db.get(Product, int(product_id))
        if product is None:
            return {"ok": False, "error": "상품을 찾을 수 없습니다."}
        if live_price <= 0:
            live_price, refreshed_at = _fresh_local_raw_price(db, supplier_id, raw_id)

    if live_price <= 0:
        return {
            "ok": False,
            "error": "해당 공급사 상품ID에서 신뢰할 수 있는 최신 도매가를 확인하지 못했습니다. 공급사 연동/API 또는 원본 수집 상태를 확인하세요.",
        }

    def _write() -> None:
        with get_db() as db:
            with sqlite_writer_guard(db):
                product = db.get(Product, int(product_id))
                if product is None:
                    raise ValueError("상품을 찾을 수 없습니다.")
                row = db.query(SupplierProductMap).filter_by(product_id=int(product_id)).first()
                if row is None:
                    row = SupplierProductMap(product_id=int(product_id))
                old_price = float(row.current_supply_price or product.supply_price or 0)
                row.supplier_id = supplier_id
                row.raw_id = raw_id
                row.match_type = "manual_verified"
                row.confidence = 1.0
                row.verified = True
                row.previous_supply_price = old_price
                row.current_supply_price = live_price
                row.last_refreshed_at = refreshed_at or _utcnow()
                row.last_error = ""
                product.supply_price = live_price
                db.add(row)
                db.add(product)
                db.add(SupplyPriceSnapshot(
                    product_id=int(product_id),
                    supplier_id=supplier_id,
                    raw_id=raw_id,
                    old_price=old_price,
                    new_price=live_price,
                    change_rate=((live_price - old_price) / old_price) if old_price > 0 else 0.0,
                    status="manual_map",
                ))
                db.commit()

    retry_sqlite_write(_write, attempts=8)
    return {
        "ok": True,
        "product_id": int(product_id),
        "supplier_id": supplier_id,
        "raw_id": raw_id,
        "supply_price": live_price,
        "supplier_name": live_name,
    }


def repair_supplier_mappings(*, max_refresh: int = 500) -> dict[str, Any]:
    """Rebuild deterministic lineage and refresh every mapped price possible."""
    rebuilt = rebuild_supplier_mappings()
    refreshed = refresh_supplier_prices(max_items=max_refresh)
    unresolved = list_unresolved_supplier_products(limit=max_refresh)
    return {
        "ok": True,
        "rebuilt": rebuilt,
        "refreshed": refreshed,
        "unresolved_count": len(unresolved),
    }


def list_supplier_mappings(limit: int = 1000) -> list[dict[str, Any]]:
    ensure_pricing_schema()
    with get_db() as db:
        rows = (
            db.query(SupplierProductMap, Product)
            .join(Product, Product.id == SupplierProductMap.product_id)
            .order_by(SupplierProductMap.updated_at.desc())
            .limit(limit)
            .all()
        )
        now = _utcnow()
        out = []
        for mapping, product in rows:
            age_hours = None
            if mapping.last_refreshed_at:
                age_hours = max(0.0, (now - mapping.last_refreshed_at).total_seconds() / 3600)
            out.append({
                "product_id": product.id,
                "상품명": product.name,
                "공급사": mapping.supplier_id,
                "공급사상품ID": mapping.raw_id,
                "매칭": mapping.match_type,
                "신뢰도": round(float(mapping.confidence or 0) * 100, 1),
                "검증": bool(mapping.verified),
                "현재도매가": float(mapping.current_supply_price or 0),
                "이전도매가": float(mapping.previous_supply_price or 0),
                "갱신경과(시간)": round(age_hours, 1) if age_hours is not None else None,
                "최근오류": mapping.last_error or "",
            })
        return out


def supply_price_history(limit: int = 300) -> list[dict[str, Any]]:
    ensure_pricing_schema()
    with get_db() as db:
        rows = (
            db.query(SupplyPriceSnapshot)
            .order_by(SupplyPriceSnapshot.checked_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "시각": x.checked_at,
                "상품ID": x.product_id,
                "공급사": x.supplier_id,
                "공급사상품ID": x.raw_id,
                "이전도매가": x.old_price,
                "최신도매가": x.new_price,
                "변동률(%)": round(float(x.change_rate or 0) * 100, 2),
                "상태": x.status,
                "오류": x.error,
            }
            for x in rows
        ]


def classify_price_risk(
    *,
    eligible: bool,
    supply_price: float,
    current_price: float,
    margin_rate: float,
    target_margin_rate: float,
    supply_fresh: bool,
    supply_safe: bool,
) -> tuple[str, str]:
    if supply_price <= 0:
        return "BLOCKED", "도매가 미확인"
    if not supply_safe:
        return "BLOCKED", "도매 상품 매핑 검증 필요"
    if not supply_fresh:
        return "BLOCKED", f"도매가가 {int(DEFAULT_MAX_SUPPLY_AGE_HOURS)}시간 이상 최신화되지 않음"
    if current_price <= 0 or not eligible:
        return "BLOCKED", "현재 판매가/수수료 확인 필요"
    if margin_rate < 0:
        return "CRITICAL", "현재 판매가 기준 적자"
    if margin_rate < target_margin_rate - 0.10:
        return "HIGH", "목표마진보다 10%p 이상 부족"
    if margin_rate < target_margin_rate:
        return "WARNING", "목표마진 미달"
    if margin_rate > target_margin_rate + 0.20:
        return "REVIEW", "목표마진보다 20%p 이상 높음 · 가격 경쟁력 검토"
    return "OK", "목표마진 범위 정상"


def persist_price_risks(rows: list[Any], target_margin_rate: float) -> dict[str, int]:
    ensure_pricing_schema()
    counts = {"CRITICAL": 0, "HIGH": 0, "WARNING": 0, "OK": 0, "REVIEW": 0, "BLOCKED": 0}

    for row in rows:
        level, reason = classify_price_risk(
            eligible=bool(row.eligible),
            supply_price=float(row.supply_price or 0),
            current_price=float(row.current_price or 0),
            margin_rate=float(row.current_margin_rate or 0),
            target_margin_rate=float(target_margin_rate or 0),
            supply_fresh=bool(getattr(row, "supply_fresh", False)),
            supply_safe=bool(getattr(row, "supply_safe", False)),
        )
        counts[level] = counts.get(level, 0) + 1

        def _write() -> None:
            with get_db() as db:
                db.add(
                    PriceRiskSnapshot(
                        product_id=int(row.product_id),
                        listing_id=int(row.listing_id),
                        platform=str(row.platform),
                        platform_id=str(row.platform_id),
                        supply_price=float(row.supply_price or 0),
                        current_price=float(row.current_price or 0),
                        fee_rate=float(row.fee_rate or 0),
                        margin_rate=float(row.current_margin_rate or 0),
                        target_margin_rate=float(target_margin_rate or 0),
                        risk_level=level,
                        reason=reason,
                    )
                )
                db.commit()
        retry_sqlite_write(_write, attempts=8)

    return counts
