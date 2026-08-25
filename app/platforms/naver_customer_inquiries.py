"""Naver SmartStore buyer/customer inquiry API adapter.

Official current Commerce API endpoints:
- GET  /v1/pay-user/inquiries
- POST /v1/pay-merchant/inquiries/{inquiryNo}/answer
- PUT  /v1/pay-merchant/inquiries/{inquiryNo}/answer/{answerContentId}
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx

from app.platforms.smartstore import API, get_smartstore_uploader


def _headers() -> dict[str, str]:
    return get_smartstore_uploader()._headers()


def collect_naver_customer_inquiries(days: int = 7, page_size: int = 100) -> list[dict[str, Any]]:
    """Collect buyer inquiries and normalize them to Seller OS inquiry rows."""
    now = datetime.now().astimezone()
    start = now - timedelta(days=max(1, min(30, int(days))))
    params = {
        "inquiryTimeFrom": start.isoformat(timespec="seconds"),
        "inquiryTimeTo": now.isoformat(timespec="seconds"),
        "page": 1,
        "size": max(1, min(200, int(page_size))),
    }
    rows: list[dict[str, Any]] = []
    for page in range(1, 51):
        params["page"] = page
        r = httpx.get(f"{API}/v1/pay-user/inquiries", params=params, headers=_headers(), timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"스마트스토어 고객문의 수집 실패 HTTP {r.status_code}: {r.text[:500]}")
        raw = r.json()
        data = raw.get("data") if isinstance(raw, dict) else raw
        if isinstance(data, dict):
            items = data.get("contents") or data.get("content") or data.get("inquiries") or data.get("items") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        if not isinstance(items, list):
            items = []
        for x in items:
            inquiry_no = str(x.get("inquiryNo") or "")
            if not inquiry_no:
                continue
            product_order_ids = str(x.get("productOrderIdList") or "")
            rows.append({
                "platform": "smartstore",
                "inquiry_type": "customer",
                "external_inquiry_id": inquiry_no,
                "external_order_id": str(x.get("orderId") or ""),
                "external_item_id": product_order_ids.split(",")[0].strip() if product_order_ids else str(x.get("productNo") or ""),
                "title": str(x.get("title") or "고객 문의"),
                "question": str(x.get("inquiryContent") or ""),
                "customer_name": str(x.get("customerName") or ""),
                "category": str(x.get("category") or "customer"),
                "status": "answered" if bool(x.get("answered")) else "open",
                "answer": str(x.get("answerContent") or ""),
                "asked_at": str(x.get("inquiryRegistrationDateTime") or ""),
                "raw": x,
            })
        if len(items) < int(params["size"]):
            break
    return rows


def answer_naver_customer_inquiry(inquiry_no: str, answer: str, *, answer_content_id: str = "") -> dict[str, Any]:
    """Register a new answer, or modify an existing answer when its ID is known."""
    inquiry_no = str(inquiry_no or "").strip()
    answer = str(answer or "").strip()
    if not inquiry_no or not answer:
        return {"ok": False, "error": "문의번호와 답변이 필요합니다."}
    if answer_content_id:
        method = "PUT"
        url = f"{API}/v1/pay-merchant/inquiries/{inquiry_no}/answer/{answer_content_id}"
    else:
        method = "POST"
        url = f"{API}/v1/pay-merchant/inquiries/{inquiry_no}/answer"
    # Current API accepts answer content in the request body. Keep the local shape
    # isolated here so changes in Naver's schema do not leak into Seller OS.
    r = httpx.request(method, url, headers=_headers(), json={"answerContent": answer}, timeout=30)
    ok = r.status_code in (200, 201, 204)
    return {
        "ok": ok,
        "status_code": r.status_code,
        "data": r.json() if ok and r.content else {},
        "error": "" if ok else r.text[:1000],
    }
