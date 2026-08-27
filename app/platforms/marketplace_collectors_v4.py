"""Current marketplace collectors used by Seller OS v4.

The legacy adapters are intentionally left import-compatible. This module provides
bounded pagination, fixed query windows and normalized rows for production polling.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.platforms.coupang import get_coupang_uploader
from app.platforms.commerce_ops_api import _int, _iso, _naver_get

KST = ZoneInfo("Asia/Seoul")


def _windows(start: datetime, end: datetime, hours: int) -> list[tuple[datetime, datetime]]:
    result: list[tuple[datetime, datetime]] = []
    cursor = start
    step = timedelta(hours=max(1, int(hours)))
    while cursor < end:
        nxt = min(end, cursor + step)
        result.append((cursor, nxt))
        cursor = nxt
    return result


def collect_coupang_claims_v4(hours_back: int = 24) -> list[dict[str, Any]]:
    u = get_coupang_uploader()
    end = datetime.now(KST).replace(tzinfo=None)
    start = end - timedelta(hours=max(1, int(hours_back)))
    rows: list[dict[str, Any]] = []

    # returnRequests with searchType=timeFrame is minute-granularity and cannot be
    # paged. Split into <=24h windows so no large window silently loses records.
    for w_from, w_to in _windows(start, end, 24):
        for claim_type, cancel_type in (("return", "RETURN"), ("cancel", "CANCEL")):
            params = {
                "searchType": "timeFrame",
                "createdAtFrom": w_from.strftime("%Y-%m-%dT%H:%M"),
                "createdAtTo": w_to.strftime("%Y-%m-%dT%H:%M"),
                "cancelType": cancel_type,
            }
            path = f"/v2/providers/openapi/apis/api/v6/vendors/{u._vendor_id}/returnRequests?{urlencode(params)}"
            response = u._get(path)
            if response.status_code != 200:
                raise RuntimeError(f"쿠팡 {claim_type} 수집 실패 HTTP {response.status_code}: {response.text[:500]}")
            raw = response.json()
            data = raw.get("data") or []
            if isinstance(data, dict):
                data = data.get("content") or data.get("items") or []
            for x in data if isinstance(data, list) else []:
                receipt_id = str(x.get("receiptId") or x.get("cancelId") or x.get("returnId") or "")
                order_id = str(x.get("orderId") or "")
                items = x.get("returnItems") or x.get("cancelItems") or x.get("items") or [{}]
                if not isinstance(items, list) or not items:
                    items = [{}]
                for item in items:
                    item_id = str(item.get("orderItemId") or item.get("vendorItemId") or "")
                    rows.append({
                        "platform": "coupang",
                        "external_claim_id": receipt_id or f"{claim_type}:{order_id}:{item_id}",
                        "external_order_id": order_id,
                        "external_item_id": item_id,
                        "claim_type": claim_type,
                        "status": str(x.get("receiptStatus") or x.get("status") or "requested"),
                        "reason": str(x.get("reasonCodeText") or x.get("reasonEtcDetail") or x.get("reasonCode") or ""),
                        "raw": x,
                    })

    # Exchange API is token-paged and permits at most a 7-day query window.
    for w_from, w_to in _windows(start, end, 24 * 7):
        token = ""
        for _ in range(100):
            params: dict[str, Any] = {
                "createdAtFrom": w_from.strftime("%Y-%m-%dT%H:%M:%S"),
                "createdAtTo": w_to.strftime("%Y-%m-%dT%H:%M:%S"),
                "maxPerPage": 50,
            }
            if token:
                params["nextToken"] = token
            path = f"/v2/providers/openapi/apis/api/v4/vendors/{u._vendor_id}/exchangeRequests?{urlencode(params)}"
            response = u._get(path)
            if response.status_code != 200:
                raise RuntimeError(f"쿠팡 exchange 수집 실패 HTTP {response.status_code}: {response.text[:500]}")
            raw = response.json()
            data = raw.get("data") or []
            if isinstance(data, dict):
                items_root = data.get("content") or data.get("items") or []
                token = str(data.get("nextToken") or raw.get("nextToken") or "")
            else:
                items_root = data
                token = str(raw.get("nextToken") or "")
            for x in items_root if isinstance(items_root, list) else []:
                exchange_id = str(x.get("exchangeId") or x.get("receiptId") or "")
                order_id = str(x.get("orderId") or "")
                items = x.get("exchangeItemDtoV1s") or x.get("exchangeItems") or x.get("items") or [{}]
                if not isinstance(items, list) or not items:
                    items = [{}]
                for item in items:
                    item_id = str(item.get("orderItemId") or item.get("targetItemId") or item.get("vendorItemId") or "")
                    rows.append({
                        "platform": "coupang",
                        "external_claim_id": exchange_id or f"exchange:{order_id}:{item_id}",
                        "external_order_id": order_id,
                        "external_item_id": item_id,
                        "claim_type": "exchange",
                        "status": str(x.get("exchangeStatus") or x.get("status") or "requested"),
                        "reason": str(x.get("reasonCodeText") or x.get("reasonEtcDetail") or x.get("reasonCode") or ""),
                        "raw": x,
                    })
            if not token:
                break
    return rows


def collect_naver_claims_v4(hours_back: int = 24) -> list[dict[str, Any]]:
    end = datetime.now().astimezone()
    start = end - timedelta(hours=max(1, int(hours_back)))
    last_changed_from = start.isoformat(timespec="seconds")
    last_changed_to = end.isoformat(timespec="seconds")
    more_sequence: str | int | None = None
    rows: list[dict[str, Any]] = []

    for _ in range(200):
        params: dict[str, Any] = {
            "lastChangedFrom": last_changed_from,
            "lastChangedTo": last_changed_to,
            "limitCount": 300,
        }
        if more_sequence not in (None, ""):
            params["moreSequence"] = more_sequence
        response = _naver_get("/v1/pay-order/seller/product-orders/last-changed-statuses", params)
        if response.status_code != 200:
            raise RuntimeError(f"스마트스토어 주문 변경분 수집 실패 HTTP {response.status_code}: {response.text[:500]}")
        raw = response.json()
        data = raw.get("data") if isinstance(raw, dict) else raw
        if isinstance(data, dict):
            changes = data.get("lastChangeStatuses") or data.get("contents") or data.get("content") or []
            more = data.get("more") or {}
        elif isinstance(data, list):
            changes = data
            more = raw.get("more") if isinstance(raw, dict) else {}
        else:
            changes, more = [], {}

        for x in changes if isinstance(changes, list) else []:
            claim_type_raw = str(x.get("claimType") or "").upper()
            claim_type = {
                "CANCEL": "cancel",
                "RETURN": "return",
                "EXCHANGE": "exchange",
                "ADMIN_CANCEL": "cancel",
            }.get(claim_type_raw, "")
            if not claim_type:
                continue
            product_order_id = str(x.get("productOrderId") or "")
            claim_id = str(x.get("claimId") or x.get("claimNo") or "")
            rows.append({
                "platform": "smartstore",
                "external_claim_id": claim_id or f"{claim_type}:{product_order_id}",
                "external_order_id": str(x.get("orderId") or ""),
                "external_item_id": product_order_id,
                "claim_type": claim_type,
                "status": str(x.get("claimStatus") or x.get("lastChangedType") or "requested"),
                "reason": str(x.get("claimReason") or x.get("claimReasonCode") or ""),
                "raw": x,
            })

        if not isinstance(more, dict) or not more:
            break
        next_from = str(more.get("moreFrom") or "").strip()
        next_sequence = more.get("moreSequence")
        if not next_from or next_sequence in (None, ""):
            break
        last_changed_from = next_from
        more_sequence = next_sequence
    return rows


def _coupang_product_inquiries(days: int = 7) -> list[dict[str, Any]]:
    u = get_coupang_uploader()
    end = datetime.now(KST).date()
    start = end - timedelta(days=min(7, max(1, int(days))))
    rows: list[dict[str, Any]] = []
    page = 1
    while page <= 200:
        params = {
            "vendorId": u._vendor_id,
            "answeredType": "ALL",
            "inquiryStartAt": start.isoformat(),
            "inquiryEndAt": end.isoformat(),
            "pageNum": page,
            "pageSize": 50,
        }
        response = u._get(
            f"/v2/providers/openapi/apis/api/v5/vendors/{u._vendor_id}/onlineInquiries?{urlencode(params)}"
        )
        if response.status_code != 200:
            raise RuntimeError(f"쿠팡 상품문의 수집 실패 HTTP {response.status_code}: {response.text[:500]}")
        raw = response.json()
        data = raw.get("data") or {}
        content = data.get("content") or [] if isinstance(data, dict) else []
        for x in content if isinstance(content, list) else []:
            comments = x.get("commentDtoList") or []
            rows.append({
                "platform": "coupang",
                "inquiry_type": "product",
                "external_inquiry_id": str(x.get("inquiryId") or ""),
                "external_order_id": str((x.get("orderIds") or [""])[0] if x.get("orderIds") else ""),
                "external_item_id": str(x.get("vendorItemId") or x.get("sellerItemId") or ""),
                "title": str(x.get("productName") or "상품 문의"),
                "question": str(x.get("content") or ""),
                "customer_name": "",
                "category": "product",
                "status": "answered" if comments else "open",
                "answer": str(comments[-1].get("content") if comments else ""),
                "asked_at": _iso(x.get("inquiryAt")),
                "raw": x,
            })
        pagination = data.get("pagination") or {} if isinstance(data, dict) else {}
        total_pages = int(pagination.get("totalPages") or page)
        if page >= total_pages or not content:
            break
        page += 1
    return rows


def _coupang_callcenter_inquiries(days: int = 7) -> list[dict[str, Any]]:
    u = get_coupang_uploader()
    end = datetime.now(KST).date()
    start = end - timedelta(days=min(7, max(1, int(days))))
    rows: list[dict[str, Any]] = []
    page = 1
    while page <= 200:
        params = {
            "vendorId": u._vendor_id,
            "partnerCounselingStatus": "NONE",
            "inquiryStartAt": start.isoformat(),
            "inquiryEndAt": end.isoformat(),
            "pageNum": page,
            "pageSize": 30,
        }
        response = u._get(
            f"/v2/providers/openapi/apis/api/v5/vendors/{u._vendor_id}/callCenterInquiries?{urlencode(params)}"
        )
        if response.status_code != 200:
            raise RuntimeError(f"쿠팡 고객센터 문의 수집 실패 HTTP {response.status_code}: {response.text[:500]}")
        raw = response.json()
        data = raw.get("data") or {}
        content = data.get("content") or [] if isinstance(data, dict) else []
        for x in content if isinstance(content, list) else []:
            replies = x.get("replies") or []
            vendor_replies = [r for r in replies if str(r.get("answerType") or "").lower() == "vendor"]
            needs_answer = any(
                bool(r.get("needAnswer")) or str(r.get("partnerTransferStatus") or "").lower() == "requestanswer"
                for r in replies
            )
            vendor_items = x.get("vendorItemId") or []
            if not isinstance(vendor_items, list):
                vendor_items = [vendor_items]
            rows.append({
                "platform": "coupang",
                "inquiry_type": "customer",
                "external_inquiry_id": str(x.get("inquiryId") or ""),
                "external_order_id": str(x.get("orderId") or ""),
                "external_item_id": str(vendor_items[0] if vendor_items else ""),
                "title": str(x.get("itemName") or "쿠팡 고객센터 문의"),
                "question": str(x.get("content") or ""),
                "customer_name": "",
                "category": str(x.get("receiptCategory") or "customer"),
                "status": "open" if needs_answer and not vendor_replies else "answered",
                "answer": str(vendor_replies[-1].get("content") if vendor_replies else ""),
                "asked_at": _iso(x.get("inquiryAt")),
                "raw": x,
            })
        pagination = data.get("pagination") or {} if isinstance(data, dict) else {}
        total_pages = int(pagination.get("totalPages") or page)
        if page >= total_pages or not content:
            break
        page += 1
    return rows


def collect_coupang_inquiries_v4(days: int = 7) -> list[dict[str, Any]]:
    return _coupang_product_inquiries(days) + _coupang_callcenter_inquiries(days)


def answer_coupang_callcenter_inquiry_v4(inquiry_id: str, answer: str, raw: dict[str, Any]) -> dict[str, Any]:
    u = get_coupang_uploader()
    replies = raw.get("replies") or [] if isinstance(raw, dict) else []
    parent = next(
        (
            r for r in reversed(replies)
            if bool(r.get("needAnswer")) or str(r.get("partnerTransferStatus") or "").lower() == "requestanswer"
        ),
        None,
    )
    parent_answer_id = str((parent or {}).get("answerId") or "")
    if not parent_answer_id:
        return {"ok": False, "error": "쿠팡 고객센터 문의의 parentAnswerId를 확인하지 못했습니다."}
    if not getattr(u, "_vendor_user_id", ""):
        return {"ok": False, "error": "COUPANG_VENDOR_USER_ID가 필요합니다."}
    body = {
        "vendorId": u._vendor_id,
        "inquiryId": str(inquiry_id),
        "content": str(answer)[:1000],
        "replyBy": u._vendor_user_id,
        "parentAnswerId": parent_answer_id,
    }
    path = f"/v2/providers/openapi/apis/api/v4/vendors/{u._vendor_id}/callCenterInquiries/{inquiry_id}/replies"
    response = u._post(path, body)
    ok = response.status_code in (200, 201, 204)
    return {
        "ok": ok,
        "status_code": response.status_code,
        "data": response.json() if ok and response.content else {},
        "error": "" if ok else response.text[:1000],
    }


def collect_coupang_settlements_v4(days: int = 7) -> list[dict[str, Any]]:
    u = get_coupang_uploader()
    end = datetime.now(KST).date() - timedelta(days=1)
    start = end - timedelta(days=max(0, min(31, int(days)) - 1))
    token = ""
    rows: list[dict[str, Any]] = []
    for _ in range(200):
        params = {
            "vendorId": u._vendor_id,
            "recognitionDateFrom": start.isoformat(),
            "recognitionDateTo": end.isoformat(),
            "token": token,
            "maxPerPage": 50,
        }
        response = u._get(f"/v2/providers/openapi/apis/api/v1/revenue-history?{urlencode(params)}")
        if response.status_code != 200:
            raise RuntimeError(f"쿠팡 정산 수집 실패 HTTP {response.status_code}: {response.text[:500]}")
        raw = response.json()
        data = raw.get("data") or []
        page_rows = data.get("content") or data.get("items") or [] if isinstance(data, dict) else data
        for sale in page_rows if isinstance(page_rows, list) else []:
            order_id = str(sale.get("orderId") or "")
            delivery = sale.get("deliveryFee") or {}
            sale_items = sale.get("items") or [{}]
            for item in sale_items if isinstance(sale_items, list) else [{}]:
                rows.append({
                    "platform": "coupang",
                    "external_key": f"{sale.get('recognitionDate')}:{order_id}:{item.get('vendorItemId') or 'delivery'}:{sale.get('saleType')}",
                    "external_order_id": order_id,
                    "external_item_id": str(item.get("vendorItemId") or item.get("orderItemId") or ""),
                    "settlement_type": str(sale.get("saleType") or "SALE").lower(),
                    "recognition_date": str(sale.get("recognitionDate") or ""),
                    "settlement_date": str(sale.get("settlementDate") or ""),
                    "gross_revenue_krw": _int(item.get("saleAmount") or item.get("salePrice")),
                    "platform_fee_krw": _int(item.get("serviceFee")) + _int(item.get("serviceFeeVat")),
                    "shipping_amount_krw": _int(delivery.get("amount")),
                    "settlement_amount_krw": _int(item.get("settlementAmount")),
                    "quantity": _int(item.get("quantity")),
                    "raw": {"sale": sale, "item": item},
                })
        next_token = ""
        if isinstance(data, dict):
            next_token = str(data.get("nextToken") or "")
        next_token = next_token or str(raw.get("nextToken") or "")
        if not next_token or next_token == token:
            break
        token = next_token
    return rows
