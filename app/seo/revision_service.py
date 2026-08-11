"""SeoRevision CRUD + 상태 전이 + 라이브 반영 오케스트레이션.

상태 흐름: DRAFT → REVIEW_PENDING → APPROVED|REJECTED → APPLIED|APPLY_FAILED
검수(사람 승인)를 거치지 않고는 라이브 상품에 반영되지 않는다
(app/config.py:seo_review_mode_enabled, 항상 True — 끌 수 없는 안전장치).

쿠팡 반영(update_seller_product)은 실제 계정으로 검증되지 않은 엔드포인트이므로
"실험적" 플래그(_EXPERIMENTAL_PLATFORMS)로 표시한다 — GUI에서 사용자가 명시적으로
확인 체크박스를 눌러야만 반영 버튼이 활성화된다.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime

from app.db import Listing, Product, SeoRevision, get_db
from app.seo import competitor as competitor_mod
from app.seo import keyword_gen, title_gen
from app.seo.duplicate_detector import find_duplicates
from app.seo.rewriter import rewrite_detail_html
from app.seo.seo_score import score_seo

logger = logging.getLogger(__name__)

_APPLICABLE_PLATFORMS = {"smartstore", "coupang"}   # 자동 반영 가능한 플랫폼
_EXPERIMENTAL_PLATFORMS = {"coupang"}               # 실제 계정 미검증 — GUI에서 별도 확인 필요


def _append_history(revision: SeoRevision, status: str) -> None:
    history = json.loads(revision.state_history or "[]")
    history.append({"status": status, "ts": datetime.utcnow().isoformat()})
    revision.state_history = json.dumps(history, ensure_ascii=False)
    revision.status = status


def _to_dict(r: SeoRevision) -> dict:
    return {
        "id": r.id, "product_id": r.product_id, "platform": r.platform,
        "status": r.status, "state_history": json.loads(r.state_history or "[]"),
        "original_name": r.original_name,
        "original_keywords": json.loads(r.original_keywords or "[]"),
        "original_detail_html": r.original_detail_html,
        "suggested_names": json.loads(r.suggested_names or "[]"),
        "suggested_keywords": json.loads(r.suggested_keywords or "[]"),
        "suggested_detail_html": r.suggested_detail_html,
        "competitor_summary": json.loads(r.competitor_summary or "{}"),
        "duplicate_of_product_id": r.duplicate_of_product_id,
        "score_before": r.score_before, "score_after": r.score_after,
        "score_breakdown": json.loads(r.score_breakdown or "{}"),
        "reviewed_at": r.reviewed_at, "reviewed_by": r.reviewed_by,
        "applied_at": r.applied_at, "error": r.error,
        "created_at": r.created_at, "can_auto_apply": r.platform in _APPLICABLE_PLATFORMS,
        "experimental": r.platform in _EXPERIMENTAL_PLATFORMS,
    }


def analyze_product(product_id: int, platform: str, competitor_url: str = "") -> dict:
    """상품 1건을 분석해 SEO 재작성 제안(SeoRevision, status=DRAFT)을 생성한다."""
    with get_db() as db:
        p = db.query(Product).filter_by(id=product_id).first()
        if not p:
            return {"ok": False, "error": "상품을 찾을 수 없습니다"}
        original_name, category, original_detail_html = p.name, p.category, p.detail_html or ""

    keywords_result = keyword_gen.generate_keywords(product_id)
    titles = title_gen.generate_title_candidates(product_id)
    best_title = titles[0] if titles else original_name
    detail_html = rewrite_detail_html(product_id, platform, keywords_result["keywords"])
    dupes = find_duplicates(product_id)

    score_before = score_seo(product_id, original_name, category,
                             keywords_result["keywords"], detail_html, platform)
    score_after = score_seo(product_id, best_title, category,
                            keywords_result["keywords"], detail_html, platform)

    competitor_summary: dict = {}
    if competitor_url:
        competitor_summary = competitor_mod.analyze_competitor(competitor_url)

    with get_db() as db:
        revision = SeoRevision(
            product_id=product_id, platform=platform,
            original_name=original_name,
            original_keywords=json.dumps([], ensure_ascii=False),
            original_detail_html=original_detail_html,
            suggested_names=json.dumps(titles, ensure_ascii=False),
            suggested_keywords=json.dumps(keywords_result["keywords"], ensure_ascii=False),
            suggested_detail_html=detail_html,
            competitor_summary=json.dumps(competitor_summary, ensure_ascii=False),
            duplicate_of_product_id=dupes[0]["product_id"] if dupes else None,
            score_before=score_before.total, score_after=score_after.total,
            score_breakdown=json.dumps(
                {"before": score_before.breakdown, "after": score_after.breakdown},
                ensure_ascii=False,
            ),
        )
        _append_history(revision, "DRAFT")
        db.add(revision)
        db.commit()
        db.refresh(revision)
        return {"ok": True, "revision": _to_dict(revision)}


def list_revisions(status: str = "", platform: str = "") -> list[dict]:
    with get_db() as db:
        q = db.query(SeoRevision)
        if status:
            q = q.filter_by(status=status)
        if platform:
            q = q.filter_by(platform=platform)
        rows = q.order_by(SeoRevision.created_at.desc()).all()
        return [_to_dict(r) for r in rows]


def get_revision(revision_id: int) -> dict | None:
    with get_db() as db:
        r = db.query(SeoRevision).filter_by(id=revision_id).first()
        return _to_dict(r) if r else None


def submit_for_review(revision_id: int) -> dict:
    with get_db() as db:
        r = db.query(SeoRevision).filter_by(id=revision_id).first()
        if not r or r.status != "DRAFT":
            return {"ok": False, "error": "검수 요청 가능한 상태가 아닙니다"}
        _append_history(r, "REVIEW_PENDING")
        db.commit()
        return {"ok": True}


def approve_revision(revision_id: int, reviewer: str = "") -> dict:
    with get_db() as db:
        r = db.query(SeoRevision).filter_by(id=revision_id).first()
        if not r or r.status not in ("DRAFT", "REVIEW_PENDING"):
            return {"ok": False, "error": "승인 가능한 상태가 아닙니다"}
        r.reviewed_at = datetime.utcnow()
        r.reviewed_by = reviewer
        _append_history(r, "APPROVED")
        db.commit()
        return {"ok": True}


def reject_revision(revision_id: int, reason: str = "", reviewer: str = "") -> dict:
    with get_db() as db:
        r = db.query(SeoRevision).filter_by(id=revision_id).first()
        if not r or r.status not in ("DRAFT", "REVIEW_PENDING"):
            return {"ok": False, "error": "반려 가능한 상태가 아닙니다"}
        r.reviewed_at = datetime.utcnow()
        r.reviewed_by = reviewer
        r.error = reason
        _append_history(r, "REJECTED")
        db.commit()
        return {"ok": True}


def apply_revision(revision_id: int) -> dict:
    """승인된 제안을 실제 플랫폼에 반영한다 (스마트스토어만 자동 반영 가능)."""
    with get_db() as db:
        r = db.query(SeoRevision).filter_by(id=revision_id).first()
        if not r or r.status != "APPROVED":
            return {"ok": False, "error": "승인된 건만 반영할 수 있습니다"}

        if r.platform not in _APPLICABLE_PLATFORMS:
            return {"ok": False, "error": (
                f"{r.platform}은(는) 검증된 상품수정 API가 없어 자동 반영을 지원하지 않습니다. "
                "Excel로 내보내 관리자 화면에서 수동으로 반영하세요."
            )}

        listing = db.query(Listing).filter_by(
            product_id=r.product_id, platform=r.platform, status="success"
        ).first()
        if not listing or not listing.platform_id:
            return {"ok": False, "error": "등록된 리스팅 정보를 찾을 수 없습니다"}

        names = json.loads(r.suggested_names or "[]")
        new_name = names[0] if names else r.original_name

        from app.hardening.circuit_breaker import CircuitOpenError, get_circuit_breaker
        from app.hardening.rate_limiter import get_rate_limiter

        svc = "smartstore_api" if r.platform == "smartstore" else "coupang_api"

        try:
            rl = get_rate_limiter(svc)
            if not rl.acquire(timeout=8):
                r.error = "Rate limit — 잠시 후 재시도"
                db.commit()
                return {"ok": False, "error": r.error}

            cb = get_circuit_breaker(svc)
            if r.platform == "smartstore":
                from app.platforms.smartstore import get_smartstore_uploader
                result = cb.call(lambda: get_smartstore_uploader().update_product_content(
                    listing.platform_id, name=new_name, detail_html=r.suggested_detail_html,
                ))
            else:
                from app.platforms.coupang import get_coupang_uploader
                result = cb.call(lambda: get_coupang_uploader().update_seller_product(
                    listing.platform_id, name=new_name, detail_html=r.suggested_detail_html,
                ))
            if result.get("ok"):
                r.applied_at = datetime.utcnow()
                _append_history(r, "APPLIED")
                db.commit()
                return {"ok": True}

            r.error = result.get("error", "알 수 없는 오류")
            _append_history(r, "APPLY_FAILED")
            db.commit()
            return {"ok": False, "error": r.error}

        except CircuitOpenError as exc:
            r.error = str(exc)
            _append_history(r, "APPLY_FAILED")
            db.commit()
            return {"ok": False, "error": r.error}
        except Exception as exc:
            logger.error("SEO 반영 실패 [revision=%s]: %s", revision_id, exc)
            r.error = str(exc)
            _append_history(r, "APPLY_FAILED")
            db.commit()
            return {"ok": False, "error": str(exc)}
