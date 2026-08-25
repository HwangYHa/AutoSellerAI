"""Marketplace operations gateway for Seller OS automation.

Keeps claims, inquiries, settlement and inventory/sale-state APIs separate from
product publishing code. Responses are normalized conservatively because both
marketplaces evolve response envelopes independently from the business fields.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.platforms.coupang import get_coupang_uploader
from app.platforms.smartstore import API as NAVER_API, get_smartstore_uploader


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _contents(raw: Any) -> list[dict[str, Any]]:
    """Extract common list envelopes without inventing data."""
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if not isinstance(raw, dict):
        return []
    candidates = [
        raw.get("content"), raw.get("contents"), raw.get("data"),
        _dict(raw.get("data")).get("content"), _dict(raw.get("data")).get("contents"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [x for x in candidate if isinstance(x, dict)]
    return []


class MarketplaceGatewayError(RuntimeError):
    pass


class CoupangOperationsGateway:
    platform = "coupang"

    def __init__(self) -> None:
        self.client = get_coupang_uploader()
        self.vendor_id = str(getattr(self.client, "_vendor_id", "") or "").strip()
        if not self.vendor_id:
            raise MarketplaceGatewayError("COUPANG_VENDOR_ID가 설정되지 않았습니다.")

    def _get_json(self, path: str) -> dict[str, Any]:
        r = self.client._get(path)
        if r.status_code != 200:
            raise MarketplaceGatewayError(f"쿠팡 GET {r.status_code}: {r.text[:500]}")
        raw = r.json()
        if isinstance(raw, dict) and str(raw.get("code") or "").upper() in {"ERROR", "FAIL"}:
            raise MarketplaceGatewayError(str(raw.get("message") or raw)[:500])
        return _dict(raw)

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = self.client._post(path, body)
        if r.status_code not in (200, 201):
            raise MarketplaceGatewayError(f"쿠팡 POST {r.status_code}: {r.text[:500]}")
        raw = r.json()
        if isinstance(raw, dict) and str(raw.get("code") or "").upper() in {"ERROR", "FAIL"}:
            raise MarketplaceGatewayError(str(raw.get("message") or raw)[:500])
        return _dict(raw)

    def list_claims(self, days: int = 7) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=min(max(1, int(days)), 7))
        start_s = start.strftime("%Y-%m-%dT%H:%M:%S")
        end_s = now.strftime("%Y-%m-%dT%H:%M:%S")
        out: list[dict[str, Any]] = []

        # Return/cancel requests. Coupang exposes cancellation through return requests.
        query = urlencode({"createdAtFrom": start_s, "createdAtTo": end_s, "maxPerPage": 50})
        raw = self._get_json(
            f"/v2/providers/openapi/apis/api/v6/vendors/{self.vendor_id}/returnRequests?{query}"
        )
        for row in _contents(raw):
            receipt_id = str(row.get("receiptId") or row.get("returnRequestId") or row.get("cancelId") or "")
            order_id = str(row.get("orderId") or "")
            status = str(row.get("receiptStatus") or row.get("status") or "requested").lower()
            reason = str(row.get("reasonText") or row.get("reasonCode") or row.get("reason") or "")
            items = _list(row.get("returnItems")) or _list(row.get("cancelItems")) or _list(row.get("items")) or [{}]
            for idx, item in enumerate(items):
                item = _dict(item)
                external_item_id = str(item.get("orderItemId") or item.get("vendorItemId") or "")
                out.append({
                    "platform": self.platform,
                    "external_claim_id": f"return:{receipt_id}:{external_item_id or idx}",
                    "external_order_id": order_id,
                    "external_item_id": external_item_id,
                    "claim_type": "cancel" if "cancel" in str(row.get("requestType") or "").lower() else "return",
                    "status": status,
                    "reason": reason,
                    "raw": row,
                })

        # Exchanges use a separate endpoint.
        query = urlencode({"createdAtFrom": start_s, "createdAtTo": end_s, "maxPerPage": 50})
        raw = self._get_json(
            f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/exchangeRequests?{query}"
        )
        for row in _contents(raw):
            exchange_id = str(row.get("exchangeId") or row.get("receiptId") or "")
            order_id = str(row.get("orderId") or "")
            reason = str(row.get("reasonText") or row.get("reasonCode") or row.get("reason") or "")
            items = _list(row.get("exchangeItems")) or _list(row.get("items")) or [{}]
            for idx, item in enumerate(items):
                item = _dict(item)
                external_item_id = str(item.get("orderItemId") or item.get("vendorItemId") or "")
                out.append({
                    "platform": self.platform,
                    "external_claim_id": f"exchange:{exchange_id}:{external_item_id or idx}",
                    "external_order_id": order_id,
                    "external_item_id": external_item_id,
                    "claim_type": "exchange",
                    "status": str(row.get("status") or row.get("exchangeStatus") or "requested").lower(),
                    "reason": reason,
                    "raw": row,
                })
        return out

    def list_inquiries(self, days: int = 7) -> list[dict[str, Any]]:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=min(max(1, int(days)), 7) - 1)
        query = urlencode({
            "vendorId": self.vendor_id,
            "answeredType": "ALL",
            "inquiryStartAt": start.isoformat(),
            "inquiryEndAt": today.isoformat(),
            "pageNum": 1,
            "pageSize": 50,
        })
        raw = self._get_json(
            f"/v2/providers/openapi/apis/api/v5/vendors/{self.vendor_id}/onlineInquiries?{query}"
        )
        out: list[dict[str, Any]] = []
        for row in _contents(raw):
            inquiry_id = str(row.get("inquiryId") or "")
            if not inquiry_id:
                continue
            comments = _list(row.get("commentDtoList"))
            answered = bool(comments)
            order_ids = row.get("orderIds") or []
            out.append({
                "platform": self.platform,
                "inquiry_type": "product",
                "external_inquiry_id": inquiry_id,
                "external_order_id": str(order_ids[0]) if isinstance(order_ids, list) and order_ids else "",
                "external_item_id": str(row.get("vendorItemId") or row.get("sellerItemId") or ""),
                "external_product_id": str(row.get("sellerProductId") or row.get("productId") or ""),
                "title": str(row.get("productName") or "상품문의"),
                "question": str(row.get("content") or ""),
                "customer_name": str(row.get("buyerEmail") or row.get("customerName") or ""),
                "category": str(row.get("inquiryType") or ""),
                "status": "answered" if answered else "open",
                "asked_at": row.get("inquiryAt"),
                "raw": row,
            })
        return out

    def answer_inquiry(self, external_inquiry_id: str, answer: str, *, inquiry_type: str = "product") -> dict[str, Any]:
        if inquiry_type not in {"product", "callcenter"}:
            raise MarketplaceGatewayError(f"쿠팡에서 지원하지 않는 문의 유형: {inquiry_type}")
        segment = "onlineInquiries" if inquiry_type == "product" else "callCenterInquiries"
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/{segment}/{external_inquiry_id}/replies"
        raw = self._post_json(path, {"content": str(answer)[:4000]})
        return {"ok": True, "raw": raw}

    def list_settlements(self, days: int = 31) -> list[dict[str, Any]]:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=min(max(1, int(days)), 31) - 1)
        query = urlencode({
            "vendorId": self.vendor_id,
            "recognitionDateFrom": start.isoformat(),
            "recognitionDateTo": today.isoformat(),
            "maxPerPage": 50,
        })
        out: list[dict[str, Any]] = []
        next_token = ""
        for _ in range(100):
            q = query + ("&" + urlencode({"token": next_token}) if next_token else "")
            raw = self._get_json(f"/v2/providers/openapi/apis/api/v1/revenue-history?{q}")
            rows = _contents(raw)
            for row in rows:
                items = _list(row.get("items")) or [{}]
                for idx, item in enumerate(items):
                    item = _dict(item)
                    external_key = ":".join([
                        str(row.get("orderId") or ""),
                        str(item.get("vendorItemId") or idx),
                        str(row.get("recognitionDate") or ""),
                        str(row.get("saleType") or "SALE"),
                    ])
                    sale_price = int(item.get("salePrice") or 0)
                    quantity = int(item.get("quantity") or 0)
                    service_fee = int(item.get("serviceFee") or 0)
                    settlement_amount = int(item.get("settlementAmount") or 0)
                    out.append({
                        "platform": self.platform,
                        "external_key": external_key,
                        "external_order_id": str(row.get("orderId") or ""),
                        "external_item_id": str(item.get("vendorItemId") or ""),
                        "settlement_type": str(row.get("saleType") or "sale").lower(),
                        "recognition_date": str(row.get("recognitionDate") or ""),
                        "settlement_date": str(row.get("settlementDate") or ""),
                        "gross_revenue_krw": sale_price * quantity,
                        "platform_fee_krw": service_fee,
                        "shipping_amount_krw": int(row.get("deliveryFee") or 0),
                        "settlement_amount_krw": settlement_amount,
                        "quantity": quantity,
                        "raw": {"header": row, "item": item},
                    })
            data = _dict(raw.get("data"))
            next_token = str(raw.get("nextToken") or data.get("nextToken") or "")
            if not next_token or not rows:
                break
        return out

    def set_vendor_item_stock(self, vendor_item_id: str, qty: int) -> dict[str, Any]:
        return self.client.update_vendor_item_stock(str(vendor_item_id), max(0, int(qty)))


class SmartStoreOperationsGateway:
    platform = "smartstore"

    def __init__(self) -> None:
        self.client = get_smartstore_uploader()

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = httpx.get(f"{NAVER_API}{path}", headers=self.client._headers(), params=params or {}, timeout=30)
        if r.status_code != 200:
            raise MarketplaceGatewayError(f"스마트스토어 GET {r.status_code}: {r.text[:500]}")
        return r.json()

    def _post_json(self, path: str, body: dict[str, Any]) -> Any:
        r = httpx.post(f"{NAVER_API}{path}", headers=self.client._headers(), json=body, timeout=30)
        if r.status_code not in (200, 201, 204):
            raise MarketplaceGatewayError(f"스마트스토어 POST {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}

    def _put_json(self, path: str, body: dict[str, Any]) -> Any:
        r = httpx.put(f"{NAVER_API}{path}", headers=self.client._headers(), json=body, timeout=30)
        if r.status_code not in (200, 201, 204):
            raise MarketplaceGatewayError(f"스마트스토어 PUT {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}

    def list_claims(self, hours: int = 24) -> list[dict[str, Any]]:
        # Naver recommends polling the last-changed feed frequently. We keep the
        # business window configurable and normalize only claim-requested rows.
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=max(1, min(int(hours), 24 * 30)))
        params = {
            "lastChangedFrom": start.isoformat(timespec="seconds"),
            "lastChangedTo": now.isoformat(timespec="seconds"),
            "lastChangedStatus": "CLAIM_REQUESTED",
            "limitCount": 300,
        }
        raw = self._get_json("/v1/pay-order/seller/product-orders/last-changed-statuses", params)
        out: list[dict[str, Any]] = []
        for row in _contents(raw):
            claim_type = str(row.get("claimType") or row.get("claim", {}).get("claimType") or "").lower()
            if claim_type not in {"cancel", "return", "exchange"}:
                continue
            product_order_id = str(row.get("productOrderId") or "")
            order_id = str(row.get("orderId") or "")
            external_claim_id = str(row.get("claimId") or row.get("claimNo") or f"{claim_type}:{product_order_id}:{row.get('lastChangedDate','')}")
            out.append({
                "platform": self.platform,
                "external_claim_id": external_claim_id,
                "external_order_id": order_id,
                "external_item_id": product_order_id,
                "claim_type": claim_type,
                "status": str(row.get("claimStatus") or "requested").lower(),
                "reason": str(row.get("claimReason") or row.get("reason") or ""),
                "raw": row,
            })
        return out

    def list_inquiries(self, days: int = 7) -> list[dict[str, Any]]:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=max(1, min(int(days), 30)) - 1)
        out: list[dict[str, Any]] = []

        # Product Q&A
        raw = self._get_json("/v1/contents/qnas", {
            "fromDate": start.isoformat(), "toDate": today.isoformat(), "page": 1, "size": 100,
        })
        for row in _contents(raw):
            qid = str(row.get("questionId") or row.get("id") or "")
            if not qid:
                continue
            answer = row.get("answer") or row.get("answerContent")
            out.append({
                "platform": self.platform,
                "inquiry_type": "product",
                "external_inquiry_id": qid,
                "external_order_id": "",
                "external_item_id": str(row.get("productNo") or row.get("originProductNo") or ""),
                "external_product_id": str(row.get("originProductNo") or row.get("productNo") or ""),
                "title": str(row.get("productName") or "상품문의"),
                "question": str(row.get("questionContent") or row.get("content") or ""),
                "customer_name": str(row.get("writerName") or ""),
                "category": str(row.get("questionType") or ""),
                "status": "answered" if answer else "open",
                "asked_at": row.get("createDate") or row.get("regDate"),
                "raw": row,
            })

        # Naver Pay customer inquiries.
        raw = self._get_json("/v1/pay-user/inquiries", {
            "from": start.isoformat(), "to": today.isoformat(), "page": 1, "size": 100,
        })
        for row in _contents(raw):
            ino = str(row.get("inquiryNo") or row.get("id") or "")
            if not ino:
                continue
            answer = row.get("answerContent") or row.get("answer")
            out.append({
                "platform": self.platform,
                "inquiry_type": "customer",
                "external_inquiry_id": ino,
                "external_order_id": str(row.get("orderId") or ""),
                "external_item_id": str(row.get("productOrderId") or ""),
                "external_product_id": str(row.get("originProductNo") or ""),
                "title": str(row.get("inquiryTitle") or "구매자문의"),
                "question": str(row.get("inquiryContent") or row.get("content") or ""),
                "customer_name": str(row.get("customerName") or ""),
                "category": str(row.get("inquiryType") or ""),
                "status": "answered" if answer else "open",
                "asked_at": row.get("inquiryDate") or row.get("createDate"),
                "raw": row,
            })
        return out

    def answer_inquiry(self, external_inquiry_id: str, answer: str, *, inquiry_type: str = "product") -> dict[str, Any]:
        if inquiry_type == "product":
            raw = self._put_json(f"/v1/contents/qnas/{external_inquiry_id}", {"answerContent": str(answer)[:4000]})
        elif inquiry_type == "customer":
            raw = self._post_json(f"/v1/pay-merchant/inquiries/{external_inquiry_id}/answer", {"answerContent": str(answer)[:4000]})
        else:
            raise MarketplaceGatewayError(f"스마트스토어에서 지원하지 않는 문의 유형: {inquiry_type}")
        return {"ok": True, "raw": raw}

    def list_settlements(self, days: int = 31) -> list[dict[str, Any]]:
        today = datetime.now(timezone.utc).date()
        out: list[dict[str, Any]] = []
        for offset in range(min(max(1, int(days)), 31)):
            day = today - timedelta(days=offset)
            raw = self._get_json("/v1/pay-settle/settle/daily", {"date": day.isoformat()})
            for idx, row in enumerate(_contents(raw)):
                external_key = str(row.get("settlementNo") or row.get("productOrderId") or f"{day.isoformat()}:{idx}")
                amount = int(row.get("settlementAmount") or row.get("settleAmount") or row.get("paySettleAmount") or 0)
                sales = int(row.get("saleAmount") or row.get("paymentAmount") or row.get("salesAmount") or 0)
                fee = int(row.get("commissionAmount") or row.get("feeAmount") or max(0, sales - amount))
                out.append({
                    "platform": self.platform,
                    "external_key": external_key,
                    "external_order_id": str(row.get("orderId") or ""),
                    "external_item_id": str(row.get("productOrderId") or ""),
                    "settlement_type": str(row.get("settlementType") or "sale").lower(),
                    "recognition_date": str(row.get("recognitionDate") or day.isoformat()),
                    "settlement_date": str(row.get("settlementDate") or day.isoformat()),
                    "gross_revenue_krw": sales,
                    "platform_fee_krw": fee,
                    "shipping_amount_krw": int(row.get("deliveryFeeAmount") or row.get("shippingAmount") or 0),
                    "settlement_amount_krw": amount,
                    "quantity": int(row.get("quantity") or 0),
                    "raw": row,
                })
        return out

    def get_origin_product(self, origin_product_no: str) -> dict[str, Any]:
        raw = self._get_json(f"/v2/products/{origin_product_no}")
        return _dict(raw)

    def set_sale_status(self, origin_product_no: str, status_type: str) -> dict[str, Any]:
        raw = self._put_json(
            f"/v1/products/origin-products/{origin_product_no}/change-status",
            {"statusType": str(status_type).upper()},
        )
        return {"ok": True, "raw": raw}

    def set_stock(self, origin_product_no: str, qty: int) -> dict[str, Any]:
        # Existing updater performs a full GET/PUT and therefore preserves fields
        # Naver requires on product update. Option stock must be handled separately.
        return self.client.update_stock(str(origin_product_no), "", max(0, int(qty)))


def get_marketplace_gateway(platform: str):
    platform = str(platform or "").strip().lower()
    if platform == "coupang":
        return CoupangOperationsGateway()
    if platform == "smartstore":
        return SmartStoreOperationsGateway()
    raise MarketplaceGatewayError(f"지원하지 않는 판매채널: {platform}")
