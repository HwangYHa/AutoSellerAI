"""온채널 판매 승인 관리자 (OnchanelApprovalManager).

[온채널 승인 프로세스]
  1. AI_SCORED → APPROVAL_PENDING  : batch_request_approvals() 에서 일괄 판단
  2. APPROVAL_PENDING → APPROVAL_REQUESTED : request_sale() 로 판매신청 POST
  3. APPROVAL_REQUESTED → APPROVED/REJECTED : check_approval_status() 폴링
  4. REJECTED → APPROVAL_PENDING (재시도 횟수 < max_retries)

[기술 구현]
  - 온채널 로그인 세션 유지 (requests.Session)
  - 판매신청: POST /mypage/apply-sale 혹은 동등한 엔드포인트
  - 결과 폴링: /mypage/product-status 페이지 스크래핑
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from app.config import get_settings
from app.suppliers.workflow import WFState, transition

logger = logging.getLogger(__name__)

ONCHANNEL_BASE = "https://www.onchannel.net"
_SESSION: requests.Session | None = None
_SESSION_EXPIRES: datetime | None = None
_SESSION_TTL = 3600  # 1시간


# ── 세션 관리 ──────────────────────────────────────────────────────────────────

def _get_session() -> requests.Session:
    global _SESSION, _SESSION_EXPIRES
    now = datetime.utcnow()
    if _SESSION and _SESSION_EXPIRES and now < _SESSION_EXPIRES:
        return _SESSION

    s = get_settings()
    if not s.onchannel_login_id or not s.onchannel_login_pw:
        raise RuntimeError("온채널 로그인 정보가 설정되어 있지 않습니다.")

    sess = requests.Session()
    sess.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # 로그인
    login_url = f"{ONCHANNEL_BASE}/member/login_ok.php"
    resp = sess.post(login_url, data={
        "login_id":  s.onchannel_login_id,
        "login_pw":  s.onchannel_login_pw,
        "auto_login": "N",
    }, timeout=15, allow_redirects=True)
    resp.raise_for_status()

    if "로그아웃" not in resp.text and "logout" not in resp.text.lower():
        raise RuntimeError("온채널 로그인 실패 — 아이디/비밀번호 확인 필요")

    _SESSION = sess
    _SESSION_EXPIRES = now + timedelta(seconds=_SESSION_TTL)
    logger.info("온채널 세션 갱신 완료")
    return sess


def _reset_session():
    global _SESSION, _SESSION_EXPIRES
    _SESSION = None
    _SESSION_EXPIRES = None


# ── 판매 신청 ──────────────────────────────────────────────────────────────────

def request_sale(onchannel_product_id: str, workflow_item_id: int) -> dict:
    """온채널 판매 신청을 요청한다.

    Returns: {"ok": bool, "message": str}
    """
    try:
        sess = _get_session()
    except RuntimeError as e:
        return {"ok": False, "message": str(e)}

    try:
        # 1) 판매신청 엔드포인트 (사이트 구조에 따라 달라질 수 있음)
        apply_url = f"{ONCHANNEL_BASE}/product/seller_apply.php"
        resp = sess.post(apply_url, data={
            "no": onchannel_product_id,
            "mode": "apply",
        }, timeout=15)

        if resp.status_code == 401 or "로그인" in resp.text:
            _reset_session()
            return {"ok": False, "message": "세션 만료 — 재로그인 필요"}

        # 응답 본문에서 결과 추출
        if resp.ok and ("신청완료" in resp.text or "success" in resp.text.lower()):
            # 워크플로우 상태 전이: APPROVAL_PENDING → APPROVAL_REQUESTED
            t_result = transition(
                workflow_item_id,
                WFState.APPROVAL_REQUESTED,
                extra={"applied_at": datetime.utcnow().isoformat()},
            )
            if not t_result["ok"]:
                logger.warning("WF 전이 실패: %s", t_result)

            # DB 업데이트
            _update_approval_fields(
                workflow_item_id,
                approval_status="REQUESTED",
                approval_requested_at=datetime.utcnow(),
            )
            return {"ok": True, "message": f"판매 신청 완료: {onchannel_product_id}"}

        # 실패 케이스 파싱
        soup = BeautifulSoup(resp.text, "html.parser")
        error_msg = soup.find("div", class_="error") or soup.find("p", class_="msg")
        msg = error_msg.get_text(strip=True) if error_msg else f"HTTP {resp.status_code}"
        return {"ok": False, "message": msg}

    except Exception as exc:
        logger.error("온채널 판매신청 실패 [%s]: %s", onchannel_product_id, exc)
        return {"ok": False, "message": str(exc)}


# ── 승인 상태 확인 ─────────────────────────────────────────────────────────────

def check_approval_status(onchannel_product_id: str, workflow_item_id: int) -> dict:
    """온채널에서 승인 결과를 폴링한다.

    Returns: {"status": "PENDING"|"APPROVED"|"REJECTED", "reason": str}
    """
    try:
        sess = _get_session()
    except RuntimeError as e:
        return {"status": "PENDING", "reason": str(e)}

    try:
        status_url = f"{ONCHANNEL_BASE}/mypage/product_status.php"
        resp = sess.get(status_url, params={"no": onchannel_product_id}, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # 승인 상태 텍스트 파싱 (실제 사이트 DOM 구조에 맞게 조정 필요)
        status_el = soup.find("span", class_="approval-status") or \
                    soup.find("td", class_="status")

        if not status_el:
            # 상품 목록 테이블에서 찾기
            rows = soup.find_all("tr")
            for row in rows:
                if onchannel_product_id in row.get_text():
                    cells = row.find_all("td")
                    if len(cells) >= 4:
                        status_text = cells[3].get_text(strip=True)
                        return _parse_status_text(status_text, workflow_item_id)

            return {"status": "PENDING", "reason": "상태 정보를 찾을 수 없음"}

        status_text = status_el.get_text(strip=True)
        return _parse_status_text(status_text, workflow_item_id)

    except Exception as exc:
        logger.error("승인 상태 확인 실패 [%s]: %s", onchannel_product_id, exc)
        return {"status": "PENDING", "reason": str(exc)}


def _parse_status_text(text: str, workflow_item_id: int) -> dict:
    """사이트 텍스트에서 승인 상태를 파싱하고 WF 상태를 전이한다."""
    text_lower = text.lower()

    if any(k in text for k in ("승인완료", "판매가능", "APPROVED", "approved")):
        transition(workflow_item_id, WFState.APPROVED,
                   extra={"approved_at": datetime.utcnow().isoformat()})
        _update_approval_fields(workflow_item_id,
                                approval_status="APPROVED",
                                approval_result_at=datetime.utcnow())
        return {"status": "APPROVED", "reason": ""}

    if any(k in text for k in ("거절", "반려", "REJECTED", "rejected", "불가")):
        reason = re.search(r'사유[:\s]*(.+)', text)
        reject_reason = reason.group(1)[:200] if reason else text[:100]
        _handle_rejection(workflow_item_id, reject_reason)
        return {"status": "REJECTED", "reason": reject_reason}

    if any(k in text for k in ("검토중", "대기", "PENDING", "신청중")):
        return {"status": "PENDING", "reason": text}

    # 알 수 없는 텍스트는 PENDING으로 처리
    return {"status": "PENDING", "reason": f"상태 파싱 불가: {text[:50]}"}


def _handle_rejection(workflow_item_id: int, reason: str):
    """거절 처리: 재시도 횟수 확인 후 APPROVAL_PENDING 또는 영구 REJECTED."""
    from app.db import get_db, SupplierWorkflowItem

    with get_db() as db:
        item = db.query(SupplierWorkflowItem).filter_by(id=workflow_item_id).first()
        if not item:
            return

        item.approval_retry_count = (item.approval_retry_count or 0) + 1
        item.approval_reject_reason = reason[:400]
        item.approval_result_at = datetime.utcnow()

        max_retries = item.approval_max_retries or 2

        if item.approval_retry_count < max_retries:
            # 재시도 가능 → APPROVAL_PENDING으로 되돌림
            db.commit()
            transition(workflow_item_id, WFState.APPROVAL_PENDING,
                       extra={"retry": item.approval_retry_count, "prev_reason": reason})
            logger.info("온채널 승인 거절 — 재신청 예약 [retry=%d/%d]",
                        item.approval_retry_count, max_retries)
        else:
            # 최대 재시도 초과 → 영구 REJECTED
            db.commit()
            transition(workflow_item_id, WFState.REJECTED,
                       error_msg=f"최대 재시도 초과({max_retries}): {reason}")
            logger.warning("온채널 승인 거절 — 재시도 불가 [%d]", workflow_item_id)


def _update_approval_fields(workflow_item_id: int, **kwargs):
    from app.db import get_db, SupplierWorkflowItem

    with get_db() as db:
        item = db.query(SupplierWorkflowItem).filter_by(id=workflow_item_id).first()
        if not item:
            return
        for k, v in kwargs.items():
            if hasattr(item, k):
                setattr(item, k, v)
        db.commit()


# ── 일괄 처리 ──────────────────────────────────────────────────────────────────

def batch_request_approvals(min_score: float = 80.0, limit: int = 20) -> dict:
    """AI_SCORED 상태의 온채널 상품 중 min_score 이상인 것들에 대해 판매신청을 요청한다.

    Returns: {"requested": int, "skipped": int, "errors": int}
    """
    from app.db import get_db, SupplierWorkflowItem

    with get_db() as db:
        items = db.query(SupplierWorkflowItem).filter_by(
            supplier_id="onchannel",
            workflow_state=WFState.AI_SCORED,
        ).filter(
            SupplierWorkflowItem.ai_score >= min_score
        ).limit(limit).all()

    stats = {"requested": 0, "skipped": 0, "errors": 0, "details": []}

    for item in items:
        # APPROVAL_PENDING 전이 먼저 (AI_SCORED → APPROVAL_PENDING)
        t = transition(item.id, WFState.APPROVAL_PENDING)
        if not t["ok"]:
            stats["errors"] += 1
            continue

        time.sleep(0.5)  # 온채널 서버 부하 방지

        result = request_sale(item.raw_id, item.id)
        if result["ok"]:
            stats["requested"] += 1
            stats["details"].append({"id": item.id, "name": item.product_name[:30], "ok": True})
        else:
            stats["errors"] += 1
            stats["details"].append({
                "id": item.id, "name": item.product_name[:30],
                "ok": False, "error": result["message"],
            })

    logger.info("온채널 일괄 판매신청 완료: %s", stats)
    return stats


def monitor_approvals(limit: int = 50) -> dict:
    """APPROVAL_REQUESTED 상태 아이템들의 승인 결과를 폴링한다.

    Returns: {"approved": int, "rejected": int, "pending": int}
    """
    from app.db import get_db, SupplierWorkflowItem

    with get_db() as db:
        items = db.query(SupplierWorkflowItem).filter_by(
            supplier_id="onchannel",
            workflow_state=WFState.APPROVAL_REQUESTED,
        ).limit(limit).all()

    stats = {"approved": 0, "rejected": 0, "pending": 0}

    for item in items:
        time.sleep(0.3)
        result = check_approval_status(item.raw_id, item.id)

        if result["status"] == "APPROVED":
            stats["approved"] += 1
        elif result["status"] == "REJECTED":
            stats["rejected"] += 1
        else:
            stats["pending"] += 1

    logger.info("온채널 승인 모니터링 완료: %s", stats)
    return stats
