"""Marketplace-wide SEO diagnostic, classification and user-approved optimization.

The engine intentionally separates three things that are often mixed together:
1) facts available from the marketplace seller APIs,
2) locally observed sales/performance signals,
3) recommended edits.

There is no promise of a search rank.  The goal is to remove objective product
information defects and improve search relevance while preserving the operator's
final decision for every live change.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import desc

from app.db import Listing, Order, PlatformOrder, Product, ProductPerformance, get_db
from app.seo.market_api import CoupangSeoApi, LOCKED_FIELDS, NaverSeoApi, SEO_WRITE_FIELDS
from app.seo.market_models import MarketSeoApplyLog, MarketSeoAudit, ensure_market_seo_schema


_PROMO_WORDS = (
    "초특가", "최저가", "무료배송", "특가", "핫딜", "베스트", "인기상품", "강력추천",
    "추천상품", "신상품", "신상", "대박", "필수템", "고급", "프리미엄",
)
_GENERIC_WORDS = {"상품", "제품", "용품", "신형", "최신", "다용도", "고급", "프리미엄"}
_CLASS_LABELS = {
    "NO_EXPOSURE_SIGNAL": "노출 신호 부족",
    "LOW_CTR_SIGNAL": "노출 대비 클릭 부족",
    "LOW_CONVERSION_SIGNAL": "클릭 대비 구매 부족",
    "HAS_SALES_PROTECT": "판매이력 보호",
    "SEO_STRUCTURE_FIRST": "상품정보/SEO 구조 우선 개선",
    "HEALTHY": "현재 구조 양호",
}


@dataclass
class AuditIssue:
    code: str
    area: str
    severity: str
    title: str
    reason: str
    current: Any = ""
    recommended: Any = ""
    field: str = ""
    auto_applicable: bool = False
    locked: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code, "area": self.area, "severity": self.severity,
            "title": self.title, "reason": self.reason, "current": self.current,
            "recommended": self.recommended, "field": self.field,
            "auto_applicable": self.auto_applicable, "locked": self.locked,
        }


@dataclass
class AuditResult:
    product_id: int
    listing_id: int
    platform: str
    platform_product_id: str
    product_name: str
    current: dict[str, Any]
    proposed: dict[str, Any]
    issues: list[AuditIssue] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    data_sources: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    quality_score: float = 0.0
    proposed_score: float = 0.0
    opportunity_score: float = 0.0
    priority_grade: str = "C"
    classification: str = "SEO_STRUCTURE_FIRST"
    recent_orders: int = 0
    sales_protected: bool = False
    audit_id: int | None = None
    batch_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.audit_id,
            "batch_id": self.batch_id,
            "product_id": self.product_id,
            "listing_id": self.listing_id,
            "platform": self.platform,
            "platform_product_id": self.platform_product_id,
            "product_name": self.product_name,
            "current": self.current,
            "proposed": self.proposed,
            "issues": [x.as_dict() for x in self.issues],
            "evidence": self.evidence,
            "data_sources": self.data_sources,
            "limitations": self.limitations,
            "quality_score": self.quality_score,
            "proposed_score": self.proposed_score,
            "opportunity_score": self.opportunity_score,
            "priority_grade": self.priority_grade,
            "classification": self.classification,
            "classification_label": _CLASS_LABELS.get(self.classification, self.classification),
            "recent_orders": self.recent_orders,
            "sales_protected": self.sales_protected,
            "critical_count": sum(1 for x in self.issues if x.severity == "critical"),
            "warning_count": sum(1 for x in self.issues if x.severity == "warning"),
            "issue_count": len(self.issues),
        }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _tokens(*values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = re.sub(r"[^0-9A-Za-z가-힣]+", " ", str(value or ""))
        for token in text.split():
            token = token.strip()
            key = token.casefold()
            if len(token) < 2 or key in seen or token in _GENERIC_WORDS:
                continue
            seen.add(key)
            out.append(token)
    return out


def normalize_title(name: str, brand: str = "", *, max_len: int = 100) -> str:
    """Remove promotional noise without inventing specifications."""
    text = str(name or "").strip()
    for word in _PROMO_WORDS:
        text = re.sub(re.escape(word), " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[|,/;]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts: list[str] = []
    seen: set[str] = set()
    if brand:
        brand_clean = re.sub(r"\s+", " ", str(brand)).strip()
        if brand_clean and brand_clean.casefold() not in text.casefold():
            parts.append(brand_clean)
            seen.add(brand_clean.casefold())
    for token in text.split():
        key = token.casefold()
        if key and key not in seen:
            parts.append(token)
            seen.add(key)
    result = " ".join(parts).strip()
    return result[:max_len].rstrip() or str(name or "")[:max_len]


def keyword_candidates(product: Product | dict[str, Any], current: dict[str, Any], *, max_count: int) -> list[str]:
    if isinstance(product, dict):
        name = product.get("name", ""); category = product.get("category", "")
        brand = product.get("brand", ""); material = product.get("material", "")
    else:
        name, category, brand, material = product.name, product.category, product.brand, product.material
    base = _tokens(current.get("title"), name, category, brand, material)
    result: list[str] = []
    seen: set[str] = set()
    for text in base:
        key = text.casefold()
        if key not in seen:
            result.append(text); seen.add(key)
    # Use only combinations composed of facts already present in the product.
    nouns = base[:7]
    for i in range(len(nouns)):
        for j in range(i + 1, min(i + 4, len(nouns))):
            phrase = f"{nouns[i]} {nouns[j]}".strip()
            key = phrase.casefold()
            if len(phrase) <= 20 and key not in seen:
                result.append(phrase); seen.add(key)
            if len(result) >= max_count:
                return result[:max_count]
    return result[:max_count]


def _current_tag_texts(current: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in current.get("tags") or []:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _performance(product_id: int, platform: str, days: int = 30) -> dict[str, Any]:
    cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
    with get_db() as db:
        rows = (
            db.query(ProductPerformance)
            .filter(ProductPerformance.product_id == product_id)
            .filter(ProductPerformance.platform == platform)
            .filter(ProductPerformance.snapshot_date >= cutoff)
            .all()
        )
        platform_orders = (
            db.query(PlatformOrder)
            .filter(PlatformOrder.product_id == product_id)
            .filter(PlatformOrder.platform == platform)
            .filter(PlatformOrder.ordered_at >= datetime.utcnow() - timedelta(days=days))
            .count()
        )
        legacy_orders = 0
        if not platform_orders:
            legacy_orders = (
                db.query(Order)
                .filter(Order.product_id == product_id)
                .filter(Order.platform == platform)
                .filter(Order.ordered_at >= datetime.utcnow() - timedelta(days=days))
                .count()
            )
    impressions = sum(int(x.impressions or 0) for x in rows)
    clicks = sum(int(x.clicks or 0) for x in rows)
    perf_orders = sum(int(x.orders or 0) for x in rows)
    orders = max(int(platform_orders or legacy_orders or 0), perf_orders)
    return {
        "has_traffic_metrics": bool(rows),
        "impressions": impressions,
        "clicks": clicks,
        "orders": orders,
        "ctr": clicks / impressions if impressions else 0.0,
        "cvr": orders / clicks if clicks else 0.0,
        "window_days": days,
    }


def classify_performance(perf: dict[str, Any], quality_score: float) -> str:
    orders = int(perf.get("orders") or 0)
    if perf.get("has_traffic_metrics"):
        impressions = int(perf.get("impressions") or 0)
        clicks = int(perf.get("clicks") or 0)
        ctr = float(perf.get("ctr") or 0)
        cvr = float(perf.get("cvr") or 0)
        if orders > 0:
            return "HAS_SALES_PROTECT"
        if impressions < 50:
            return "NO_EXPOSURE_SIGNAL"
        if ctr < 0.01:
            return "LOW_CTR_SIGNAL"
        if clicks >= 10 and cvr < 0.02:
            return "LOW_CONVERSION_SIGNAL"
    elif orders > 0:
        return "HAS_SALES_PROTECT"
    return "HEALTHY" if quality_score >= 85 else "SEO_STRUCTURE_FIRST"


def _issue_penalty(issue: AuditIssue) -> float:
    return {"critical": 14.0, "warning": 7.0, "info": 2.0}.get(issue.severity, 3.0)


def _score(issues: Iterable[AuditIssue]) -> float:
    return round(max(0.0, 100.0 - sum(_issue_penalty(x) for x in issues)), 1)


def _priority(score: float, recent_orders: int, classification: str) -> tuple[float, str]:
    opportunity = min(100.0, max(0.0, 100.0 - score + min(recent_orders, 5) * 6.0))
    if classification == "HAS_SALES_PROTECT":
        opportunity = min(100.0, opportunity + 10.0)
    if opportunity >= 70:
        grade = "S"
    elif opportunity >= 50:
        grade = "A"
    elif opportunity >= 30:
        grade = "B"
    else:
        grade = "C"
    return round(opportunity, 1), grade


def _coupang_required_attributes(meta: dict) -> list[str]:
    attrs = meta.get("attributes") or []
    result: list[str] = []
    grouped: dict[str, list[str]] = {}
    for raw in attrs if isinstance(attrs, list) else []:
        if not isinstance(raw, dict) or str(raw.get("exposed") or "").upper() != "EXPOSED":
            continue
        name = str(raw.get("attributeTypeName") or "").strip()
        if not name:
            continue
        required = str(raw.get("required") or "").upper()
        group = str(raw.get("groupNumber") or "NONE").upper()
        if required == "MANDATORY" and group == "NONE":
            result.append(name)
        elif required == "OPTIONAL" and group not in ("", "NONE"):
            grouped.setdefault(group, []).append(name)
    # A grouped requirement means at least one of the group should be present. Keep a
    # readable synthetic marker; the diagnostic checks any member rather than all.
    for names in grouped.values():
        if names:
            result.append(" | ".join(names))
    return result


def _missing_coupang_attributes(required: list[str], current_attrs: list[dict]) -> list[str]:
    present = {
        str(x.get("attributeTypeName") or "").strip()
        for x in current_attrs if str(x.get("attributeValueName") or "").strip()
    }
    missing: list[str] = []
    for requirement in required:
        alternatives = [x.strip() for x in requirement.split("|") if x.strip()]
        if alternatives and not any(x in present for x in alternatives):
            missing.append(requirement)
    return missing


def _naver_required_attributes(meta_attrs: list[dict]) -> list[dict]:
    result = []
    for item in meta_attrs:
        required = item.get("required") is True or str(item.get("requiredYn") or item.get("mandatory") or "").upper() in {"Y", "TRUE", "MANDATORY"}
        if required:
            result.append(item)
    return result


class MarketSeoOptimizer:
    """Orchestrates remote audit, persistence, selection and live application."""

    def __init__(self, coupang_api=None, naver_api=None):
        ensure_market_seo_schema()
        self.coupang = coupang_api or CoupangSeoApi()
        self.naver = naver_api or NaverSeoApi()
        self._coupang_meta_cache: dict[str, tuple[dict, str]] = {}
        self._naver_category_cache: dict[str, tuple[dict, str]] = {}
        self._naver_attr_cache: dict[str, tuple[list[dict], str]] = {}
        self._naver_inspections: tuple[list[dict], str] | None = None

    @staticmethod
    def capabilities() -> dict[str, Any]:
        return {
            "coupang": {
                "read": ["전체 상품 목록", "상품 상세", "카테고리 유효성", "카테고리 메타정보", "카테고리 추천", "상태변경이력", "주문(로컬 수집)"],
                "write": ["노출상품명/일반상품명", "검색어(searchTags)", "상세콘텐츠", "확인된 브랜드"],
                "locked": ["카테고리", "가격", "배송비/배송정책", "대표이미지", "필수속성값 자동추측"],
            },
            "smartstore": {
                "read": ["상품 목록", "v2 원상품", "v2 채널상품", "카테고리", "카테고리 속성", "추천 태그", "제한 태그", "상품 검수", "카탈로그 후보", "주문(로컬 수집)"],
                "write": ["상품명/SEO pageTitle", "sellerTags", "상세콘텐츠/metaDescription", "확인된 브랜드"],
                "locked": ["카테고리", "가격", "배송비/배송정책", "대표이미지", "속성값 자동추측"],
            },
            "not_public": ["실시간 검색순위", "쿠팡/네이버 내부 랭킹 점수", "공개 API로 제공되지 않는 노출/클릭 지표"],
        }

    @staticmethod
    def sync_catalog(platforms: Iterable[str]) -> dict[str, dict]:
        from app.sync.catalog_sync import sync_coupang_catalog, sync_smartstore_catalog
        out: dict[str, dict] = {}
        for platform in platforms:
            if platform == "coupang":
                out[platform] = sync_coupang_catalog(max_pages=50)
            elif platform == "smartstore":
                out[platform] = sync_smartstore_catalog(max_pages=50)
        return out

    @staticmethod
    def _targets(platforms: set[str], product_ids: set[int] | None = None) -> list[dict[str, Any]]:
        with get_db() as db:
            q = (
                db.query(Listing, Product)
                .join(Product, Product.id == Listing.product_id)
                .filter(Listing.status == "success")
                .filter(Listing.platform.in_(platforms))
            )
            if product_ids:
                q = q.filter(Product.id.in_(product_ids))
            rows = q.order_by(Product.updated_at.desc()).all()
            return [{
                "listing_id": listing.id,
                "product_id": product.id,
                "platform": listing.platform,
                "platform_product_id": listing.platform_id,
                "product": {
                    "id": product.id, "name": product.name, "category": product.category,
                    "brand": product.brand, "origin": product.origin, "material": product.material,
                    "sell_price": product.sell_price, "supply_price": product.supply_price,
                    "detail_html": product.detail_html or "", "sku": product.sku,
                },
            } for listing, product in rows]

    def audit_all(self, platforms: Iterable[str] = ("coupang", "smartstore"), *, deep: bool = True) -> list[dict]:
        return self.audit_selected(platforms=platforms, product_ids=None, deep=deep)

    def audit_selected(self, *, platforms: Iterable[str], product_ids: Iterable[int] | None, deep: bool = True) -> list[dict]:
        platform_set = {x for x in platforms if x in {"coupang", "smartstore"}}
        ids = {int(x) for x in product_ids} if product_ids else None
        batch_id = f"seo-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        results: list[dict] = []
        for target in self._targets(platform_set, ids):
            try:
                audit = self.audit_target(target, deep=deep)
                audit.batch_id = batch_id
                self._persist(audit)
                results.append(audit.as_dict())
            except Exception as exc:
                fallback = AuditResult(
                    product_id=target["product_id"], listing_id=target["listing_id"],
                    platform=target["platform"], platform_product_id=target["platform_product_id"],
                    product_name=target["product"]["name"], current={}, proposed={},
                    issues=[AuditIssue("REMOTE_AUDIT_FAILED", "API", "critical", "원격 정밀진단 실패", str(exc))],
                    limitations=[str(exc)], batch_id=batch_id,
                )
                fallback.quality_score = 0.0; fallback.proposed_score = 0.0
                fallback.opportunity_score = 100.0; fallback.priority_grade = "S"
                self._persist(fallback, error=str(exc))
                results.append(fallback.as_dict())
        return results

    def audit_target(self, target: dict[str, Any], *, deep: bool = True) -> AuditResult:
        if target["platform"] == "coupang":
            return self._audit_coupang(target, deep=deep)
        return self._audit_naver(target, deep=deep)

    def _common_issues(self, product: dict, current: dict, proposed: dict, platform: str) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        title = str(current.get("title") or "")
        proposed_title = str(proposed.get("title") or title)
        if not title:
            issues.append(AuditIssue("TITLE_MISSING", "상품명", "critical", "노출 상품명이 비어 있음", "검색 적합도를 판단할 핵심 상품명이 없습니다.", title, proposed_title, "title", True))
        else:
            if any(word in title for word in _PROMO_WORDS):
                issues.append(AuditIssue("TITLE_PROMO_NOISE", "상품명", "warning", "상품명에 광고성/모호 표현 포함", "핵심 명칭·용도·규격보다 광고성 표현이 앞서면 검색 의도가 흐려집니다.", title, proposed_title, "title", True))
            tokens = [x.casefold() for x in title.split()]
            if len(tokens) != len(set(tokens)):
                issues.append(AuditIssue("TITLE_DUPLICATE", "상품명", "warning", "상품명 중복 단어", "동일 단어 반복을 제거해 가독성과 검색 의도 일관성을 높입니다.", title, proposed_title, "title", True))
            if len(title) < 8:
                issues.append(AuditIssue("TITLE_TOO_SHORT", "상품명", "warning", "상품명이 지나치게 짧음", "상품을 구분할 실제 속성이 충분히 표현되지 않았을 수 있습니다.", title, proposed_title, "title", True))
            if len(title) > 100:
                issues.append(AuditIssue("TITLE_TOO_LONG", "상품명", "critical", "상품명 API 권장 길이 초과", "플랫폼 상품명 제한과 모바일 가독성을 확인해야 합니다.", len(title), len(proposed_title), "title", True))
        if not str(current.get("brand") or "").strip() and str(product.get("brand") or "").strip():
            issues.append(AuditIssue("BRAND_MISSING", "브랜드", "warning", "플랫폼 브랜드 누락", "로컬/공급처에 확인된 브랜드가 있으나 플랫폼 상품정보에는 비어 있습니다.", "", product.get("brand"), "brand", True))
        if int(current.get("image_count") or 0) < 1:
            issues.append(AuditIssue("REP_IMAGE_MISSING", "대표이미지", "critical", "대표이미지 누락", "검색목록 클릭 이전에 반드시 필요한 상품 식별 정보입니다.", 0, "대표이미지 확인/등록", "images", False, True))
        elif int(current.get("image_count") or 0) == 1:
            issues.append(AuditIssue("IMAGE_VARIETY_LOW", "이미지", "info", "이미지가 대표 1장뿐", "추가 각도·디테일 이미지가 있으면 상품 이해와 전환 진단에 유리합니다.", 1, "추가 이미지 검토", "images", False, True))
        if not current.get("detail_present"):
            issues.append(AuditIssue("DETAIL_MISSING", "상세페이지", "critical", "상세정보 누락", "구매 전 필요한 규격·대상·사용 정보를 확인하기 어렵습니다.", "없음", "확인된 원본 정보로 상세정보 작성", "detail", bool(product.get("detail_html"))))
        return issues

    def _audit_coupang(self, target: dict[str, Any], *, deep: bool) -> AuditResult:
        detail = self.coupang.get_product(target["platform_product_id"])
        current = self.coupang.current_fields(detail)
        product = target["product"]
        proposed_title = normalize_title(current.get("title") or product["name"], current.get("brand") or product.get("brand"))
        proposed_tags = keyword_candidates(product, current, max_count=20)
        proposed = {
            "title": proposed_title,
            "general_product_name": normalize_title(proposed_title, ""),
            "brand": current.get("brand") or product.get("brand") or "",
            "tags": proposed_tags,
            "detail_html": product.get("detail_html") or "",
            "category": current.get("category"),
            "price": product.get("sell_price"),
            "shipping": {"type": current.get("delivery_charge_type"), "charge": current.get("delivery_charge")},
        }
        issues = self._common_issues(product, current, proposed, "coupang")
        sources: dict[str, Any] = {"product_detail": "ok"}
        evidence: dict[str, Any] = {}
        limitations: list[str] = []

        tag_texts = _current_tag_texts(current)
        if not tag_texts:
            issues.append(AuditIssue("COUPANG_TAGS_EMPTY", "검색어", "warning", "쿠팡 searchTags 미입력", "쿠팡 공개 상품 API가 제공하는 검색어 필드가 비어 있습니다.", [], proposed_tags, "tags", True))
        elif len(tag_texts) > 20 or any(len(x) > 20 for x in tag_texts):
            issues.append(AuditIssue("COUPANG_TAGS_LIMIT", "검색어", "critical", "검색어 제한 재점검", "검색어는 개수/개별 길이 제한에 맞춰 정리해야 합니다.", tag_texts, proposed_tags, "tags", True))
        if len({x.casefold() for x in tag_texts}) < len(tag_texts):
            issues.append(AuditIssue("COUPANG_TAGS_DUPLICATE", "검색어", "warning", "중복 검색어", "동일 검색어를 중복 사용하지 않습니다.", tag_texts, proposed_tags, "tags", True))

        cat = str(current.get("category") or "")
        valid, valid_note = self.coupang.category_valid(cat)
        sources["category_validity"] = valid_note
        evidence["category_valid"] = valid
        if valid is False:
            issues.append(AuditIssue("COUPANG_CATEGORY_OFF", "카테고리", "warning", "현재 카테고리 유효성 재확인", "기존 상품은 카테고리 리뉴얼 후에도 노출될 수 있으므로 자동 변경하지 않고 추천만 제공합니다.", cat, "카테고리 추천 확인", "category", False, True))
        if cat not in self._coupang_meta_cache:
            self._coupang_meta_cache[cat] = self.coupang.get_category_metadata(cat)
        meta, meta_note = self._coupang_meta_cache[cat]
        sources["category_metadata"] = meta_note
        required = _coupang_required_attributes(meta)
        missing = _missing_coupang_attributes(required, current.get("attributes") or [])
        evidence["required_attributes"] = required
        evidence["missing_required_attributes"] = missing
        if missing:
            issues.append(AuditIssue("COUPANG_REQUIRED_ATTR_MISSING", "검색/구매옵션", "critical", "카테고리 필수/그룹 구매옵션 누락 가능", "카테고리 메타정보의 MANDATORY/그룹 EXPOSED 조건과 현재 옵션값을 비교했습니다. 실제 값은 추측하지 않습니다.", missing, "실제 상품 스펙 확인 후 입력", "attributes", False, True))
        if deep and (valid is False or not cat):
            rec, rec_note = self.coupang.recommend_category(product)
            sources["category_recommendation"] = rec_note
            evidence["category_recommendation"] = rec
        histories, hist_note = self.coupang.get_histories(target["platform_product_id"], max_pages=2) if deep else ([], "skipped")
        sources["status_histories"] = hist_note
        evidence["status_histories"] = histories[-10:]
        rejection_text = _json(histories).lower()
        if any(x in rejection_text for x in ("반려", "reject", "violation")):
            issues.append(AuditIssue("COUPANG_HISTORY_REJECTION", "상품상태", "warning", "반려/위반 이력 확인 필요", "상품 상태변경이력 API에서 반려 또는 위반 관련 신호가 보입니다.", "이력 존재", "Wing 사유 확인", "", False, True))
        if "승인완료" not in str(current.get("status") or "") and str(current.get("status") or ""):
            issues.append(AuditIssue("COUPANG_NOT_APPROVED", "판매상태", "critical", "승인완료 상태 아님", "검색 최적화보다 판매 가능 상태를 먼저 확인해야 합니다.", current.get("status"), "승인/판매상태 확인", "", False, True))

        return self._finish(target, current, proposed, issues, evidence, sources, limitations)

    def _audit_naver(self, target: dict[str, Any], *, deep: bool) -> AuditResult:
        payload = self.naver.get_product(target["platform_product_id"])
        current = self.naver.current_fields(payload)
        product = target["product"]
        proposed_title = normalize_title(current.get("title") or product["name"], current.get("brand") or product.get("brand"))
        tag_candidates = keyword_candidates(product, current, max_count=10)
        recommended_tag_objects: list[dict] = []
        sources: dict[str, Any] = {"origin_product_v2": "ok"}
        evidence: dict[str, Any] = {}
        limitations: list[str] = []

        if deep and tag_candidates:
            rec_tags, rec_note = self.naver.recommend_tags(tag_candidates[0])
            sources["recommend_tags"] = rec_note
            # Prefer exact API-backed tags, then append direct fact-based candidates.
            for row in rec_tags:
                text = str(row.get("text") or row.get("name") or "").strip()
                if text:
                    recommended_tag_objects.append({"code": row.get("code"), "text": text})
            existing_texts = {str(x.get("text") or "").casefold() for x in recommended_tag_objects}
            for text in tag_candidates:
                if text.casefold() not in existing_texts:
                    recommended_tag_objects.append({"text": text})
                if len(recommended_tag_objects) >= 10:
                    break
        else:
            recommended_tag_objects = [{"text": x} for x in tag_candidates]
            sources["recommend_tags"] = "skipped"

        candidate_texts = [str(x.get("text") or "") for x in recommended_tag_objects if str(x.get("text") or "")]
        restricted: dict[str, bool] = {}
        if deep and candidate_texts:
            restricted, restrict_note = self.naver.restricted_tags(candidate_texts)
            sources["restricted_tags"] = restrict_note
            if restricted:
                recommended_tag_objects = [x for x in recommended_tag_objects if not restricted.get(str(x.get("text") or ""), False)]
        else:
            sources["restricted_tags"] = "skipped"

        proposed = {
            "title": proposed_title,
            "page_title": proposed_title,
            "brand": current.get("brand") or product.get("brand") or "",
            "tags": recommended_tag_objects[:10],
            "detail_html": product.get("detail_html") or current.get("detail_html") or "",
            "meta_description": re.sub(r"<[^>]+>", " ", product.get("detail_html") or current.get("detail_html") or "")[:160],
            "category": current.get("category"),
            "price": current.get("sale_price"),
            "shipping": current.get("delivery") or {},
        }
        issues = self._common_issues(product, current, proposed, "smartstore")
        current_tags = _current_tag_texts(current)
        if not current_tags:
            issues.append(AuditIssue("NAVER_TAGS_EMPTY", "검색태그", "warning", "네이버 sellerTags 미입력", "검색 적합성에 활용할 수 있는 판매자 태그가 없습니다.", [], proposed["tags"], "tags", True))
        if restricted:
            bad_current = [x for x in current_tags if restricted.get(x, False)]
            if bad_current:
                issues.append(AuditIssue("NAVER_RESTRICTED_TAG", "검색태그", "critical", "제한 태그 포함", "제한 태그 API 결과를 기준으로 제거 검토가 필요합니다.", bad_current, "제거", "tags", True))

        category_id = str(current.get("category") or "")
        if category_id not in self._naver_category_cache:
            self._naver_category_cache[category_id] = self.naver.get_category(category_id)
        category_info, category_note = self._naver_category_cache[category_id]
        sources["category"] = category_note
        evidence["category_info"] = category_info
        if not category_id:
            issues.append(AuditIssue("NAVER_CATEGORY_MISSING", "카테고리", "critical", "리프 카테고리 없음", "검색 분류의 기본 정보가 없습니다.", "", "판매자센터에서 정확한 카테고리 확인", "category", False, True))
        if category_id not in self._naver_attr_cache:
            self._naver_attr_cache[category_id] = self.naver.get_category_attributes(category_id)
        attr_meta, attr_note = self._naver_attr_cache[category_id]
        sources["category_attributes"] = attr_note
        required = _naver_required_attributes(attr_meta)
        current_attr_ids = {str(x.get("attributeSeq") or x.get("attributeId") or "") for x in current.get("attributes") or []}
        missing_required = []
        for item in required:
            aid = str(item.get("attributeSeq") or item.get("attributeId") or "")
            if aid and aid not in current_attr_ids:
                missing_required.append(item.get("attributeName") or item.get("name") or aid)
        evidence["missing_required_attributes"] = missing_required
        if missing_required:
            issues.append(AuditIssue("NAVER_REQUIRED_ATTR_MISSING", "검색필터/속성", "warning", "카테고리 필수 속성 누락 가능", "카테고리 속성 API와 현재 productAttributes를 비교했습니다. 값은 자동 추측하지 않습니다.", missing_required, "실제 스펙 확인 후 입력", "attributes", False, True))

        if not current.get("brand") and not current.get("manufacturer"):
            issues.append(AuditIssue("NAVER_SEARCH_INFO_SPARSE", "쇼핑검색정보", "warning", "브랜드/제조사 검색정보 부족", "naverShoppingSearchInfo의 기본 식별정보가 부족합니다.", {"brand": current.get("brand"), "manufacturer": current.get("manufacturer")}, proposed.get("brand"), "brand", bool(proposed.get("brand"))))
        if not current.get("catalog_matching") and not current.get("catalog_product_id"):
            issues.append(AuditIssue("NAVER_CATALOG_UNMATCHED", "카탈로그", "info", "카탈로그 매칭 없음", "동일 모델 카탈로그가 존재하는 상품인지 후보를 확인할 수 있습니다. 자동 매칭하지 않습니다.", "미매칭", "카탈로그 후보 검토", "category", False, True))
            if deep:
                candidates, catalog_note = self.naver.get_catalog_candidates(_tokens(current.get("title"))[0] if _tokens(current.get("title")) else current.get("title", ""))
                sources["catalog_candidates"] = catalog_note
                evidence["catalog_candidates"] = candidates[:5]

        if self._naver_inspections is None and deep:
            self._naver_inspections = self.naver.get_inspection_requests(page=1, size=100)
        inspections, inspection_note = self._naver_inspections if self._naver_inspections is not None else ([], "skipped")
        sources["product_inspections"] = inspection_note
        origin_no = str(target["platform_product_id"])
        matched_inspections = [x for x in inspections if origin_no in _json(x)]
        evidence["inspection_requests"] = matched_inspections[:5]
        if matched_inspections:
            issues.append(AuditIssue("NAVER_INSPECTION_REQUEST", "상품검수", "critical", "네이버 수정 요청 상품", "상품 검수 API에서 수정 요청 대상과 연결되는 항목이 발견되었습니다.", "수정 요청", "사유 확인 후 우선 해결", "", False, True))
        if current.get("status") not in ("SALE", "", None):
            issues.append(AuditIssue("NAVER_NOT_SALE", "판매상태", "critical", "판매중 상태 아님", "검색 최적화보다 판매/검수 상태를 먼저 해결해야 합니다.", current.get("status"), "판매상태 확인", "", False, True))
        if int(current.get("stock") or 0) <= 0:
            issues.append(AuditIssue("NAVER_STOCK_ZERO", "재고", "critical", "재고 0", "노출/구매 가능성을 논하기 전에 판매 재고를 확인해야 합니다.", current.get("stock"), "재고 확인", "", False, True))

        return self._finish(target, current, proposed, issues, evidence, sources, limitations)

    def _finish(self, target: dict, current: dict, proposed: dict, issues: list[AuditIssue], evidence: dict, sources: dict, limitations: list[str]) -> AuditResult:
        perf = _performance(target["product_id"], target["platform"], 30)
        quality = _score(issues)
        classification = classify_performance(perf, quality)
        recent_orders = int(perf.get("orders") or 0)
        sales_protected = recent_orders > 0
        if not perf.get("has_traffic_metrics"):
            limitations.append("판매자 공개 API에서 상품별 노출·클릭을 직접 받지 못해 AutoSellerAI ProductPerformance 데이터가 없으면 해당 지표는 판정에 사용하지 않습니다.")
        # Estimate the after-score using only issues that an approved safe field can resolve.
        resolvable = [x for x in issues if x.auto_applicable and not x.locked and x.field in SEO_WRITE_FIELDS]
        proposed_score = min(100.0, round(quality + sum(_issue_penalty(x) for x in resolvable), 1))
        opportunity, grade = _priority(quality, recent_orders, classification)
        evidence["performance_30d"] = perf
        if sales_protected:
            issues.append(AuditIssue("SALES_PROTECTION", "변경안전", "info", "최근 판매이력 보호", "판매가 발생한 상품은 대규모 제목 변경을 기본적으로 보수적으로 처리합니다.", recent_orders, "사용자 최종 확인 후 적용", "title", False, True))
        return AuditResult(
            product_id=target["product_id"], listing_id=target["listing_id"],
            platform=target["platform"], platform_product_id=target["platform_product_id"],
            product_name=target["product"]["name"], current=current, proposed=proposed,
            issues=issues, evidence=evidence, data_sources=sources, limitations=limitations,
            quality_score=quality, proposed_score=proposed_score,
            opportunity_score=opportunity, priority_grade=grade,
            classification=classification, recent_orders=recent_orders,
            sales_protected=sales_protected,
        )

    def _persist(self, audit: AuditResult, error: str = "") -> None:
        data = audit.as_dict()
        with get_db() as db:
            row = MarketSeoAudit(
                batch_id=audit.batch_id, product_id=audit.product_id, listing_id=audit.listing_id,
                platform=audit.platform, platform_product_id=audit.platform_product_id,
                product_name=audit.product_name, quality_score=audit.quality_score,
                proposed_score=audit.proposed_score, opportunity_score=audit.opportunity_score,
                priority_grade=audit.priority_grade, classification=audit.classification,
                issue_count=data["issue_count"], critical_count=data["critical_count"],
                warning_count=data["warning_count"], recent_orders=audit.recent_orders,
                sales_protected=audit.sales_protected, current_json=_json(audit.current),
                proposed_json=_json(audit.proposed), issues_json=_json(data["issues"]),
                evidence_json=_json(audit.evidence), data_sources_json=_json(audit.data_sources),
                limitations_json=_json(audit.limitations), error=error,
            )
            db.add(row); db.commit(); db.refresh(row)
            audit.audit_id = row.id

    @staticmethod
    def latest_audits(platform: str = "", limit: int = 2000) -> list[dict]:
        ensure_market_seo_schema()
        with get_db() as db:
            q = db.query(MarketSeoAudit)
            if platform:
                q = q.filter(MarketSeoAudit.platform == platform)
            rows = q.order_by(desc(MarketSeoAudit.analyzed_at), desc(MarketSeoAudit.id)).limit(limit).all()
        latest: dict[int, MarketSeoAudit] = {}
        for row in rows:
            latest.setdefault(row.listing_id, row)
        return [MarketSeoOptimizer._row_dict(x) for x in latest.values()]

    @staticmethod
    def get_audit(audit_id: int) -> dict | None:
        ensure_market_seo_schema()
        with get_db() as db:
            row = db.query(MarketSeoAudit).filter_by(id=int(audit_id)).first()
            return MarketSeoOptimizer._row_dict(row) if row else None

    @staticmethod
    def _row_dict(row: MarketSeoAudit) -> dict:
        return {
            "id": row.id, "batch_id": row.batch_id, "product_id": row.product_id,
            "listing_id": row.listing_id, "platform": row.platform,
            "platform_product_id": row.platform_product_id, "product_name": row.product_name,
            "quality_score": row.quality_score, "proposed_score": row.proposed_score,
            "opportunity_score": row.opportunity_score, "priority_grade": row.priority_grade,
            "classification": row.classification,
            "classification_label": _CLASS_LABELS.get(row.classification, row.classification),
            "issue_count": row.issue_count, "critical_count": row.critical_count,
            "warning_count": row.warning_count, "recent_orders": row.recent_orders,
            "sales_protected": bool(row.sales_protected), "current": json.loads(row.current_json or "{}"),
            "proposed": json.loads(row.proposed_json or "{}"), "issues": json.loads(row.issues_json or "[]"),
            "evidence": json.loads(row.evidence_json or "{}"), "data_sources": json.loads(row.data_sources_json or "{}"),
            "limitations": json.loads(row.limitations_json or "[]"),
            "selected_fields": json.loads(row.selected_fields_json or "[]"),
            "status": row.status, "error": row.error,
            "analyzed_at": row.analyzed_at, "applied_at": row.applied_at,
        }

    def approve_fields(self, audit_id: int, fields: Iterable[str]) -> dict:
        allowed = sorted(set(fields) & SEO_WRITE_FIELDS)
        if not allowed:
            return {"ok": False, "error": "승인할 수 있는 SEO 필드가 선택되지 않았습니다."}
        with get_db() as db:
            row = db.query(MarketSeoAudit).filter_by(id=int(audit_id)).first()
            if not row:
                return {"ok": False, "error": "진단 결과를 찾을 수 없습니다."}
            row.selected_fields_json = _json(allowed)
            row.status = "APPROVED"
            db.commit()
        return {"ok": True, "fields": allowed}

    def apply_audit(self, audit_id: int, fields: Iterable[str] | None = None, *, confirm_sales_protected: bool = False) -> dict:
        with get_db() as db:
            row = db.query(MarketSeoAudit).filter_by(id=int(audit_id)).first()
            if not row:
                return {"ok": False, "error": "진단 결과를 찾을 수 없습니다."}
            proposed = json.loads(row.proposed_json or "{}")
            selected = set(fields or json.loads(row.selected_fields_json or "[]")) & SEO_WRITE_FIELDS
            if row.sales_protected and "title" in selected and not confirm_sales_protected:
                return {"ok": False, "error": "최근 판매이력이 있는 상품입니다. 제목 변경은 판매이력 보호 확인이 필요합니다."}
            if not selected:
                return {"ok": False, "error": "사용자가 승인한 자동 반영 필드가 없습니다."}
            log = MarketSeoApplyLog(
                audit_id=row.id, product_id=row.product_id, listing_id=row.listing_id,
                platform=row.platform, platform_product_id=row.platform_product_id,
                selected_fields_json=_json(sorted(selected)), status="RUNNING",
            )
            db.add(log); db.commit(); db.refresh(log)
            platform = row.platform; platform_id = row.platform_product_id

        if platform == "coupang":
            result = self.coupang.apply_fields(platform_id, proposed, selected)
        else:
            result = self.naver.apply_fields(platform_id, proposed, selected)

        with get_db() as db:
            log = db.query(MarketSeoApplyLog).filter_by(id=log.id).first()
            row = db.query(MarketSeoAudit).filter_by(id=int(audit_id)).first()
            if log:
                log.before_json = _json(result.get("before") or {})
                log.after_json = _json(result.get("after") or {})
                log.finished_at = datetime.utcnow()
                log.status = "APPLIED" if result.get("ok") else "APPLY_FAILED"
                log.error = str(result.get("error") or "")
            if row:
                row.selected_fields_json = _json(sorted(selected))
                row.applied_at = datetime.utcnow() if result.get("ok") else None
                row.status = "APPLIED" if result.get("ok") else "APPLY_FAILED"
                row.error = str(result.get("error") or "")
            db.commit()
        return {**result, "audit_id": audit_id, "fields": sorted(selected)}

    def apply_many(self, selections: dict[int, Iterable[str]], *, confirm_sales_protected: bool = False) -> dict:
        results: list[dict] = []
        for audit_id, fields in selections.items():
            results.append(self.apply_audit(int(audit_id), fields, confirm_sales_protected=confirm_sales_protected))
        return {
            "ok": all(x.get("ok") for x in results) if results else False,
            "total": len(results),
            "success": sum(1 for x in results if x.get("ok")),
            "failed": sum(1 for x in results if not x.get("ok")),
            "results": results,
        }


__all__ = [
    "AuditIssue", "AuditResult", "MarketSeoOptimizer", "classify_performance",
    "keyword_candidates", "normalize_title", "LOCKED_FIELDS", "SEO_WRITE_FIELDS",
]
