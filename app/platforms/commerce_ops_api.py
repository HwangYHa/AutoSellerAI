"""Marketplace operational API adapters for claims, inquiries, settlement and sale state.

Endpoints are based on the current official Coupang Open API and Naver Commerce API.
The functions normalize remote responses and never perform external mutations unless
called explicitly by an approved operation/service.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from app.platforms.coupang import API as COUPANG_API, get_coupang_uploader
from app.platforms.smartstore import API as NAVER_API, get_smartstore_uploader


def _iso(value: Any) -> str:
    return str(value or "")


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _naver_get(path: str, params: dict[str, Any] | None = None) -> httpx.Response:
    u = get_smartstore_uploader()
    return httpx.get(f"{NAVER_API}{path}", params=params or {}, headers=u._headers(), timeout=30)


def _naver_post(path: str, body: dict[str, Any]) -> httpx.Response:
    u = get_smartstore_uploader()
    return httpx.post(f"{NAVER_API}{path}", headers=u._headers(), json=body, timeout=30)


def _naver_put(path: str, body: dict[str, Any]) -> httpx.Response:
    u = get_smartstore_uploader()
    return httpx.put(f"{NAVER_API}{path}", headers=u._headers(), json=body, timeout=30)


def collect_coupang_claims(hours_back: int = 24) -> list[dict[str, Any]]:
    """Collect Coupang cancel/return/exchange requests.

    Official endpoints:
    - return/cancel: GET .../api/v6/vendors/{vendorId}/returnRequests
    - exchange: GET .../api/v4/vendors/{vendorId}/exchangeRequests
    """
    u = get_coupang_uploader()
    now = datetime.utcnow()
    start = now - timedelta(hours=max(1, int(hours_back)))
    rows: list[dict[str, Any]] = []

    for claim_type, cancel_type in (("return", "RETURN"), ("cancel", "CANCEL")):
        params = {
            "searchType": "timeFrame",
            "createdAtFrom": start.strftime("%Y-%m-%dT%H:%M"),
            "createdAtTo": now.strftime("%Y-%m-%dT%H:%M"),
            "cancelType": cancel_type,
        }
        path = f"/v2/providers/openapi/apis/api/v6/vendors/{u._vendor_id}/returnRequests?{urlencode(params)}"
        r = u._get(path)
        if r.status_code != 200:
            raise RuntimeError(f"쿠팡 {claim_type} 수집 실패 HTTP {r.status_code}: {r.text[:300]}")
        raw = r.json()
        data = raw.get("data") or []
        if isinstance(data, dict):
            data = data.get("content") or data.get("items") or []
        for x in data if isinstance(data, list) else []:
            receipt_id = str(x.get("receiptId") or x.get("returnId") or x.get("cancelId") or "")
            order_id = str(x.get("orderId") or "")
            reason = str(x.get("reasonCodeText") or x.get("reason") or x.get("reasonCode") or "")
            status = str(x.get("receiptStatus") or x.get("status") or "requested")
            items = x.get("returnItems") or x.get("items") or x.get("cancelItems") or [{}]
            if not isinstance(items, list) or not items:
                items = [{}]
            for item in items:
                rows.append({
                    "platform": "coupang",
                    "external_claim_id": receipt_id or f"{claim_type}:{order_id}:{item.get('vendorItemId') or item.get('orderItemId') or ''}",
                    "external_order_id": order_id,
                    "external_item_id": str(item.get("orderItemId") or item.get("vendorItemId") or ""),
                    "claim_type": claim_type,
                    "status": status,
                    "reason": reason,
                    "raw": x,
                })

    params = {
        "createdAtFrom": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "createdAtTo": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "maxPerPage": 50,
    }
    path = f"/v2/providers/openapi/apis/api/v4/vendors/{u._vendor_id}/exchangeRequests?{urlencode(params)}"
    r = u._get(path)
    if r.status_code != 200:
        raise RuntimeError(f"쿠팡 exchange 수집 실패 HTTP {r.status_code}: {r.text[:300]}")
    raw = r.json(); data = raw.get("data") or []
    if isinstance(data, dict):
        data = data.get("content") or data.get("items") or []
    for x in data if isinstance(data, list) else []:
        exchange_id = str(x.get("exchangeId") or x.get("receiptId") or "")
        order_id = str(x.get("orderId") or "")
        items = x.get("exchangeItems") or x.get("items") or [{}]
        if not isinstance(items, list) or not items:
            items = [{}]
        for item in items:
            rows.append({
                "platform": "coupang",
                "external_claim_id": exchange_id or f"exchange:{order_id}:{item.get('vendorItemId') or item.get('orderItemId') or ''}",
                "external_order_id": order_id,
                "external_item_id": str(item.get("orderItemId") or item.get("vendorItemId") or ""),
                "claim_type": "exchange",
                "status": str(x.get("status") or x.get("exchangeStatus") or "requested"),
                "reason": str(x.get("reason") or x.get("reasonCode") or ""),
                "raw": x,
            })
    return rows


def collect_naver_claims(hours_back: int = 24) -> list[dict[str, Any]]:
    """Collect SmartStore claim changes from the official last-changed order feed."""
    start = (datetime.now().astimezone() - timedelta(hours=max(1, int(hours_back)))).isoformat(timespec="seconds")
    r = _naver_get("/v1/pay-order/seller/product-orders/last-changed-statuses", {"lastChangedFrom": start, "limitCount": 300})
    if r.status_code != 200:
        raise RuntimeError(f"스마트스토어 주문 변경분 수집 실패 HTTP {r.status_code}: {r.text[:300]}")
    raw = r.json(); data = raw.get("data") or raw
    changes = data.get("lastChangeStatuses") or data.get("contents") or data.get("content") or [] if isinstance(data, dict) else []
    rows: list[dict[str, Any]] = []
    for x in changes if isinstance(changes, list) else []:
        claim_type_raw = str(x.get("claimType") or x.get("lastChangedType") or x.get("productOrderStatus") or "").upper()
        claim_type = ""
        if "CANCEL" in claim_type_raw:
            claim_type = "cancel"
        elif "RETURN" in claim_type_raw:
            claim_type = "return"
        elif "EXCHANGE" in claim_type_raw:
            claim_type = "exchange"
        if not claim_type:
            continue
        product_order_id = str(x.get("productOrderId") or "")
        order_id = str(x.get("orderId") or "")
        rows.append({
            "platform": "smartstore",
            "external_claim_id": str(x.get("claimNo") or x.get("claimId") or f"{claim_type}:{product_order_id}"),
            "external_order_id": order_id,
            "external_item_id": product_order_id,
            "claim_type": claim_type,
            "status": str(x.get("claimStatus") or x.get("lastChangedType") or "requested"),
            "reason": str(x.get("claimReason") or x.get("claimReasonCode") or ""),
            "raw": x,
        })
    return rows


def collect_coupang_inquiries(days: int = 7) -> list[dict[str, Any]]:
    u = get_coupang_uploader(); end = datetime.utcnow().date(); start = end - timedelta(days=min(7, max(1, int(days))))
    params = {"vendorId": u._vendor_id, "answeredType": "ALL", "inquiryStartAt": start.isoformat(), "inquiryEndAt": end.isoformat(), "pageNum": 1, "pageSize": 50}
    path = f"/v2/providers/openapi/apis/api/v5/vendors/{u._vendor_id}/onlineInquiries?{urlencode(params)}"
    r = u._get(path)
    if r.status_code != 200:
        raise RuntimeError(f"쿠팡 상품문의 수집 실패 HTTP {r.status_code}: {r.text[:300]}")
    raw = r.json(); content = ((raw.get("data") or {}).get("content") or []) if isinstance(raw, dict) else []
    rows = []
    for x in content:
        comments = x.get("commentDtoList") or []
        rows.append({
            "platform": "coupang", "inquiry_type": "product", "external_inquiry_id": str(x.get("inquiryId") or ""),
            "external_order_id": str((x.get("orderIds") or [""])[0] if x.get("orderIds") else ""),
            "external_item_id": str(x.get("vendorItemId") or x.get("sellerItemId") or ""),
            "title": "상품 문의", "question": str(x.get("content") or ""), "customer_name": "", "category": "product",
            "status": "answered" if comments else "open", "answer": str(comments[0].get("content") if comments else ""),
            "asked_at": _iso(x.get("inquiryAt")), "raw": x,
        })
    return rows


def answer_coupang_inquiry(inquiry_id: str, answer: str) -> dict[str, Any]:
    u = get_coupang_uploader()
    path = f"/v2/providers/openapi/apis/api/v4/vendors/{u._vendor_id}/onlineInquiries/{inquiry_id}/replies"
    r = u._post(path, {"content": str(answer)[:4000]})
    return {"ok": r.status_code in (200, 201, 204), "status_code": r.status_code, "data": (r.json() if r.content else {}), "error": "" if r.status_code in (200,201,204) else r.text[:500]}


def collect_naver_inquiries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    r = _naver_get("/v1/contents/qnas", {"page": 1, "size": 100})
    if r.status_code == 200:
        raw = r.json(); items = raw.get("contents") or raw.get("content") or raw.get("data") or [] if isinstance(raw, dict) else []
        if isinstance(items, dict): items = items.get("contents") or []
        for x in items if isinstance(items, list) else []:
            rows.append({
                "platform": "smartstore", "inquiry_type": "product", "external_inquiry_id": str(x.get("questionId") or ""),
                "external_order_id": "", "external_item_id": str(x.get("productId") or ""), "title": "상품 문의",
                "question": str(x.get("question") or ""), "customer_name": str(x.get("maskedWriterId") or ""), "category": "product",
                "status": "answered" if x.get("answered") else "open", "answer": str(x.get("answer") or ""),
                "asked_at": _iso(x.get("createDate")), "raw": x,
            })
    else:
        raise RuntimeError(f"스마트스토어 상품문의 수집 실패 HTTP {r.status_code}: {r.text[:300]}")
    return rows


def answer_naver_product_inquiry(question_id: str, answer: str) -> dict[str, Any]:
    r = _naver_put(f"/v1/contents/qnas/{question_id}", {"answer": str(answer)[:4000]})
    return {"ok": r.status_code in (200, 201, 204), "status_code": r.status_code, "data": (r.json() if r.content else {}), "error": "" if r.status_code in (200,201,204) else r.text[:500]}


def collect_coupang_settlements(days: int = 7) -> list[dict[str, Any]]:
    u = get_coupang_uploader(); end = datetime.utcnow().date() - timedelta(days=1); start = end - timedelta(days=max(0, min(30, int(days)-1)))
    token = ""; rows: list[dict[str, Any]] = []
    for _ in range(20):
        params = {"vendorId": u._vendor_id, "recognitionDateFrom": start.isoformat(), "recognitionDateTo": end.isoformat(), "token": token, "maxPerPage": 50}
        r = u._get(f"/v2/providers/openapi/apis/api/v1/revenue-history?{urlencode(params)}")
        if r.status_code != 200:
            raise RuntimeError(f"쿠팡 정산 수집 실패 HTTP {r.status_code}: {r.text[:300]}")
        raw = r.json(); data = raw.get("data") or []
        for sale in data if isinstance(data, list) else []:
            order_id = str(sale.get("orderId") or "")
            delivery = sale.get("deliveryFee") or {}
            for item in sale.get("items") or [{}]:
                rows.append({
                    "platform": "coupang",
                    "external_key": f"{sale.get('recognitionDate')}:{order_id}:{item.get('vendorItemId') or 'delivery'}:{sale.get('saleType')}",
                    "external_order_id": order_id, "external_item_id": str(item.get("vendorItemId") or ""),
                    "settlement_type": str(sale.get("saleType") or "SALE").lower(), "recognition_date": str(sale.get("recognitionDate") or ""),
                    "settlement_date": str(sale.get("settlementDate") or ""), "gross_revenue_krw": _int(item.get("saleAmount") or item.get("salePrice")),
                    "platform_fee_krw": _int(item.get("serviceFee")) + _int(item.get("serviceFeeVat")),
                    "shipping_amount_krw": _int(delivery.get("amount")), "settlement_amount_krw": _int(item.get("settlementAmount")),
                    "quantity": _int(item.get("quantity")), "raw": {"sale": sale, "item": item},
                })
        if not raw.get("hasNext"): break
        token = str(raw.get("nextToken") or "")
        if not token: break
    return rows


def collect_naver_settlements(days: int = 7) -> list[dict[str, Any]]:
    end = datetime.now().date() - timedelta(days=1); start = end - timedelta(days=max(0, int(days)-1))
    r = _naver_get("/v1/pay-settle/settle/daily", {"startDate": start.isoformat(), "endDate": end.isoformat()})
    if r.status_code != 200:
        raise RuntimeError(f"스마트스토어 정산 수집 실패 HTTP {r.status_code}: {r.text[:300]}")
    raw = r.json(); items = raw.get("data") or raw.get("contents") or raw.get("content") or raw if isinstance(raw, dict) else raw
    if isinstance(items, dict): items = items.get("contents") or items.get("items") or []
    rows = []
    for i, x in enumerate(items if isinstance(items, list) else []):
        rows.append({
            "platform": "smartstore", "external_key": str(x.get("settleNo") or x.get("settlementNo") or f"{x.get('settlementDate') or x.get('date')}:{i}"),
            "external_order_id": str(x.get("orderId") or ""), "external_item_id": str(x.get("productOrderId") or ""),
            "settlement_type": str(x.get("settlementType") or x.get("type") or "sale").lower(),
            "recognition_date": str(x.get("recognitionDate") or x.get("payDate") or ""), "settlement_date": str(x.get("settlementDate") or x.get("date") or ""),
            "gross_revenue_krw": _int(x.get("saleAmount") or x.get("salesAmount") or x.get("grossAmount")),
            "platform_fee_krw": _int(x.get("commission") or x.get("commissionAmount") or x.get("feeAmount")),
            "shipping_amount_krw": _int(x.get("deliveryFee") or x.get("shippingAmount")),
            "settlement_amount_krw": _int(x.get("settlementAmount") or x.get("settleAmount")), "quantity": _int(x.get("quantity") or 1), "raw": x,
        })
    return rows


def change_naver_sale_status(origin_product_no: str, status_type: str) -> dict[str, Any]:
    status = str(status_type or "").upper()
    if status not in {"SALE", "SUSPENSION", "OUTOFSTOCK"}:
        raise ValueError("Naver statusType must be SALE, SUSPENSION or OUTOFSTOCK")
    r = _naver_put(f"/v1/products/origin-products/{origin_product_no}/change-status", {"statusType": status})
    return {"ok": r.status_code in (200, 201, 204), "status_code": r.status_code, "data": (r.json() if r.content else {}), "error": "" if r.status_code in (200,201,204) else r.text[:500]}


def set_coupang_listing_stock(seller_product_id: str, qty: int) -> dict[str, Any]:
    """Set every vendor item under a seller product to the requested stock quantity."""
    u = get_coupang_uploader(); product = u.get_seller_product(str(seller_product_id)); results = []
    for item in product.get("items") or []:
        vendor_item_id = str(item.get("vendorItemId") or item.get("sellerProductItemId") or "")
        if not vendor_item_id:
            continue
        results.append({"vendor_item_id": vendor_item_id, **u.update_vendor_item_stock(vendor_item_id, max(0, int(qty)))})
    ok = bool(results) and all(x.get("ok") for x in results)
    return {"ok": ok, "items": results, "error": "" if ok else "일부 또는 전체 쿠팡 옵션 재고 변경 실패"}


def fetch_remote_product(platform: str, external_product_id: str) -> dict[str, Any]:
    platform = str(platform).lower()
    if platform == "coupang":
        return get_coupang_uploader().get_seller_product(str(external_product_id))
    if platform == "smartstore":
        r = _naver_get(f"/v2/products/{external_product_id}")
        if r.status_code != 200:
            raise RuntimeError(f"스마트스토어 상품조회 실패 HTTP {r.status_code}: {r.text[:300]}")
        return r.json()
    raise ValueError(f"unsupported platform: {platform}")
