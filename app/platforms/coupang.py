"""쿠팡 Wing API 업로더 (HMAC-SHA256 인증)."""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
API = "https://api-gateway.coupang.com"

_VALID_DELIVERY_CODES = {
    "CJGLS", "LOGEN", "HANJIN", "KDEXP", "POST",
    "LOTTE", "ILYANG", "DAESIN", "CHUNIL", "REGISTPOST",
    "PANTOS", "GSI", "SLX", "EPOST",
}


def _normalize_delivery_code(code: str) -> str:
    c = (code or "").strip().upper()
    return c if c in _VALID_DELIVERY_CODES else "CJGLS"


def _plain_text(value: Any, limit: int = 4000) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


class CoupangUploader:
    def __init__(self):
        s = get_settings()
        self._access_key = (s.coupang_access_key or "").strip()
        self._secret_key = (s.coupang_secret_key or "").strip()
        self._vendor_id = (s.coupang_vendor_id or "").strip()
        self._vendor_user_id = (s.coupang_vendor_user_id or "").strip()
        self._outbound_code = str(s.coupang_outbound_shipping_place_code or "").strip()
        self._return_code = str(s.coupang_return_center_code or "").strip()
        self._return_zip = (s.coupang_return_zip_code or "").strip()
        self._return_addr = (s.coupang_return_address or "").strip()
        self._return_addr_detail = (s.coupang_return_address_detail or "").strip()
        self._contact = (s.coupang_company_contact_number or "").strip()
        self._return_charge = int(s.coupang_return_charge or 0)
        self._delivery_code = _normalize_delivery_code(s.coupang_delivery_company_code or "CJGLS")
        self._debug_credentials()

    def _debug_credentials(self) -> None:
        issues = []
        if not self._access_key:
            issues.append("COUPANG_ACCESS_KEY 미설정")
        if not self._secret_key:
            issues.append("COUPANG_SECRET_KEY 미설정")
        if not self._vendor_id:
            issues.append("COUPANG_VENDOR_ID 미설정")
        elif not self._vendor_id.startswith("A"):
            issues.append("COUPANG_VENDOR_ID 형식 확인 필요")
        if issues:
            logger.warning("쿠팡 자격증명 문제 감지: %s", " / ".join(issues))

    def _sign(self, method: str, path: str, query: str = "") -> dict:
        if not self._access_key or not self._secret_key:
            raise ValueError("쿠팡 API 키가 설정되지 않았습니다.")
        datetime_gmt = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
        message = datetime_gmt + method.upper() + path + query
        sig = hmac.new(self._secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
        auth = (
            f"CEA algorithm=HmacSHA256, access-key={self._access_key}, "
            f"signed-date={datetime_gmt}, signature={sig}"
        )
        return {"Authorization": auth, "Content-Type": "application/json;charset=UTF-8"}

    def _get(self, path: str) -> httpx.Response:
        parsed = urlparse(path)
        return httpx.get(f"{API}{path}", headers=self._sign("GET", parsed.path, parsed.query), timeout=15)

    def _post(self, path: str, body: dict) -> httpx.Response:
        clean_path = urlparse(path).path
        return httpx.post(f"{API}{path}", headers=self._sign("POST", clean_path, ""), json=body, timeout=30)

    def _put(self, path: str, body: dict) -> httpx.Response:
        clean_path = urlparse(path).path
        return httpx.put(f"{API}{path}", headers=self._sign("PUT", clean_path, ""), json=body, timeout=30)

    def _require_listing_settings(self) -> None:
        missing = []
        for label, value in (
            ("COUPANG_VENDOR_ID", self._vendor_id),
            ("COUPANG_VENDOR_USER_ID", self._vendor_user_id),
            ("COUPANG_OUTBOUND_SHIPPING_PLACE_CODE", self._outbound_code),
            ("COUPANG_RETURN_CENTER_CODE", self._return_code),
            ("COUPANG_RETURN_ZIP_CODE", self._return_zip),
            ("COUPANG_RETURN_ADDRESS", self._return_addr),
            ("COUPANG_COMPANY_CONTACT_NUMBER", self._contact),
        ):
            if not value or value == "0":
                missing.append(label)
        if missing:
            raise ValueError("쿠팡 상품등록 필수 설정 누락: " + ", ".join(missing))

    def _return_center_name(self) -> str:
        if self._return_code == "NO_RETURN_CENTERCODE":
            return "직접입력 반품지"
        path = (
            "/v2/providers/openapi/apis/api/v3/return/shipping-places/center-code"
            f"?returnCenterCodes={self._return_code}"
        )
        r = self._get(path)
        if r.status_code != 200:
            raise ValueError(f"쿠팡 반품지 조회 실패 HTTP {r.status_code}: {r.text[:200]}")
        data = r.json().get("data") or []
        if isinstance(data, list) and data:
            name = str(data[0].get("shippingPlaceName") or "").strip()
            if name:
                return name
        raise ValueError("쿠팡 반품지 이름을 조회하지 못했습니다. RETURN_CENTER_CODE를 확인하세요.")

    def _category_is_valid(self, display_category_code: str | int) -> bool:
        code = str(display_category_code or "").strip()
        if not code.isdigit():
            return False
        path = (
            "/v2/providers/seller_api/apis/api/v1/marketplace/meta/"
            f"display-categories/{code}/status"
        )
        r = self._get(path)
        if r.status_code != 200:
            return False
        try:
            raw = r.json()
        except Exception:
            return False
        api_code = str(raw.get("code") or "").upper() if isinstance(raw, dict) else ""
        return api_code == "SUCCESS" and raw.get("data") is True

    def _recommend_category(self, product: dict) -> tuple[str, str]:
        name = str(product.get("name") or "").strip()
        if not name:
            raise ValueError("쿠팡 카테고리 추천에 사용할 상품명이 없습니다.")
        description_parts = [
            str(product.get("category") or ""),
            _plain_text(product.get("detail_html"), 2500),
            str(product.get("origin") or ""),
            str(product.get("material") or ""),
        ]
        body: dict[str, Any] = {
            "productName": name[:200],
            "productDescription": " ".join(x for x in description_parts if x).strip()[:4000],
            "brand": str(product.get("brand") or "")[:100],
        }
        attributes: dict[str, str] = {}
        if product.get("origin"):
            attributes["제조국"] = str(product.get("origin"))[:100]
        if product.get("material"):
            attributes["소재/원재료"] = str(product.get("material"))[:200]
        if attributes:
            body["attributes"] = attributes

        path = "/v2/providers/openapi/apis/api/v1/categorization/predict"
        r = self._post(path, body)
        if r.status_code != 200:
            raise ValueError(f"쿠팡 카테고리 추천 실패 HTTP {r.status_code}: {r.text[:400]}")
        try:
            raw = r.json()
        except Exception as exc:
            raise ValueError(f"쿠팡 카테고리 추천 응답 파싱 실패: {exc}") from exc
        data = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(data, dict):
            raise ValueError(f"쿠팡 카테고리 추천 결과 없음: {str(raw)[:400]}")
        result_type = str(data.get("autoCategorizationPredictionResultType") or "").upper()
        code = str(data.get("predictedCategoryId") or "").strip()
        category_name = str(data.get("predictedCategoryName") or "").strip()
        if result_type != "SUCCESS" or not code.isdigit():
            comment = str(data.get("comment") or raw.get("message") or "추천 실패")
            raise ValueError(f"쿠팡 카테고리 추천 실패: {comment[:300]}")
        if not self._category_is_valid(code):
            raise ValueError(
                f"쿠팡이 추천한 노출카테고리({code}{' · ' + category_name if category_name else ''})가 현재 사용 불가합니다. "
                "카테고리 재추천 또는 Wing 카테고리 확인이 필요합니다."
            )
        return code, category_name

    def _resolve_display_category(self, product: dict) -> tuple[str, str]:
        explicit = str(
            product.get("display_category_code")
            or product.get("coupang_category_code")
            or product.get("category_code")
            or ""
        ).strip()
        category_field = str(product.get("category") or "").strip()
        if not explicit and category_field.isdigit():
            explicit = category_field

        if explicit:
            if self._category_is_valid(explicit):
                return explicit, ""
            logger.warning(
                "쿠팡 지정 카테고리 %s가 유효하지 않아 상품명 기반 추천으로 재선정합니다: %s",
                explicit,
                product.get("name"),
            )

        return self._recommend_category(product)

    @staticmethod
    def _contents(product: dict, images: list[str], detail_images: list[str]) -> list[dict]:
        contents: list[dict] = []
        for url in (detail_images or images):
            contents.append({
                "contentsType": "IMAGE_NO_SPACE",
                "contentDetails": [{"content": url, "detailType": "IMAGE"}],
            })
        html = str(product.get("detail_html") or "").strip()
        if html:
            contents.append({
                "contentsType": "HTML",
                "contentDetails": [{"content": html[:50000], "detailType": "TEXT"}],
            })
        if not contents:
            contents.append({
                "contentsType": "TEXT",
                "contentDetails": [{"content": str(product.get("name") or "상품정보"), "detailType": "TEXT"}],
            })
        return contents

    def _notices(self, product: dict) -> list[dict]:
        brand = str(product.get("brand") or "상세페이지 참조")
        origin = str(product.get("origin") or "상세페이지 참조")
        return [
            {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "품명 및 모델명", "content": str(product.get("name") or "")[:100]},
            {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "인증/허가 사항", "content": "해당없음"},
            {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제조국(원산지)", "content": origin},
            {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제조자(수입자)", "content": brand},
            {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "소비자상담 관련 전화번호", "content": self._contact},
        ]

    @staticmethod
    def _build_items(product: dict, options_raw: list[dict], img_list: list[dict], notices: list[dict], contents: list[dict]) -> list[dict]:
        price = max(10, int(product["sell_price"]))
        stock = max(1, min(99999, int(product.get("stock", 999) or 999)))
        base_item: dict[str, Any] = {
            "originalPrice": price,
            "salePrice": price,
            "maximumBuyCount": stock,
            "maximumBuyForPerson": 0,
            "maximumBuyForPersonPeriod": 1,
            "outboundShippingTimeDay": 1,
            "unitCount": 1,
            "adultOnly": "EVERYONE",
            "taxType": "TAX",
            "parallelImported": "NOT_PARALLEL_IMPORTED",
            "overseasPurchased": "NOT_OVERSEAS_PURCHASED",
            "pccNeeded": False,
            "images": img_list,
            "notices": notices,
            "contents": contents,
            "certifications": [{"certificationType": "NOT_REQUIRED", "certificationCode": ""}],
            "offerCondition": "NEW",
            "offerDescription": "",
        }
        if not options_raw:
            return [{
                **base_item,
                "itemName": str(product["name"])[:150],
                "attributes": [{"attributeTypeName": "수량", "attributeValueName": "1개"}],
            }]
        opt = options_raw[0] if isinstance(options_raw[0], dict) else {}
        values = opt.get("values") or []
        if not values:
            return [{
                **base_item,
                "itemName": str(product["name"])[:150],
                "attributes": [{"attributeTypeName": "수량", "attributeValueName": "1개"}],
            }]
        items = []
        for value in values[:200]:
            option_name = str(opt.get("name") or "옵션")[:25]
            option_value = str(value)[:30]
            items.append({
                **base_item,
                "itemName": f"{str(product['name'])[:110]} {option_value}"[:150],
                "attributes": [{"attributeTypeName": option_name, "attributeValueName": option_value}],
            })
        return items

    def create_product(self, product: dict) -> dict:
        """Create a Coupang marketplace product after resolving a live valid category."""
        self._require_listing_settings()
        display_cat, display_cat_name = self._resolve_display_category(product)
        logger.info(
            "쿠팡 노출카테고리 결정 product=%s code=%s name=%s",
            str(product.get("name") or "")[:120],
            display_cat,
            display_cat_name or "(explicit)",
        )
        images = [u for u in product.get("images", []) if isinstance(u, str) and u.startswith("http")]
        detail_images = [u for u in product.get("detail_images", []) if isinstance(u, str) and u.startswith("http")]
        if not images:
            raise ValueError("쿠팡: 이미지 없음 (최소 1장 필요)")
        img_list = [
            {"imageOrder": i, "imageType": "REPRESENTATION" if i == 0 else "DETAIL", "vendorPath": u}
            for i, u in enumerate(images[:10])
        ]
        contents = self._contents(product, images, detail_images)
        notices = self._notices(product)
        items = self._build_items(product, product.get("options", []) or [], img_list, notices, contents)
        shipping_fee = max(0, int(product.get("shipping_fee", 3000) or 0))
        delivery_charge_type = "FREE" if shipping_fee == 0 else "NOT_FREE"
        return_name = self._return_center_name()
        body: dict[str, Any] = {
            "displayCategoryCode": int(display_cat),
            "sellerProductName": str(product["name"])[:100],
            "vendorId": self._vendor_id,
            "saleStartedAt": "2020-01-01T00:00:00",
            "saleEndedAt": "2099-12-31T23:59:59",
            "displayProductName": str(product["name"])[:100],
            "brand": str(product.get("brand") or "")[:100],
            "generalProductName": str(product["name"])[:100],
            "deliveryMethod": "SEQUENCIAL",
            "deliveryCompanyCode": self._delivery_code,
            "deliveryChargeType": delivery_charge_type,
            "deliveryCharge": shipping_fee,
            "freeShipOverAmount": 0,
            "deliveryChargeOnReturn": int(self._return_charge),
            "remoteAreaDeliverable": "N",
            "unionDeliveryType": "NOT_UNION_DELIVERY",
            "returnCenterCode": self._return_code,
            "returnChargeName": return_name,
            "companyContactNumber": self._contact,
            "returnZipCode": self._return_zip,
            "returnAddress": self._return_addr,
            "returnAddressDetail": self._return_addr_detail,
            "returnCharge": int(self._return_charge),
            "outboundShippingPlaceCode": int(self._outbound_code),
            "vendorUserId": self._vendor_user_id,
            "requested": True,
            "items": items,
            "manufacture": str(product.get("brand") or "상세페이지 참조")[:100],
        }
        path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
        r = self._post(path, body)
        if r.status_code == 403:
            raise ValueError(f"쿠팡 IP 미화이트리스트 (서버 IP: {self._get_public_ip()})")
        if r.status_code not in (200, 201):
            raise ValueError(f"쿠팡 API {r.status_code}: {r.text[:600]}")
        raw = r.json()
        candidate: Any = raw.get("data") if isinstance(raw, dict) else None
        if isinstance(candidate, dict):
            seller_product_id = candidate.get("sellerProductId") or candidate.get("data")
        else:
            seller_product_id = candidate
        if not seller_product_id:
            raise ValueError(f"쿠팡 상품등록 응답에서 sellerProductId를 찾지 못했습니다: {str(raw)[:500]}")
        return {
            "data": {
                "sellerProductId": str(seller_product_id),
                "displayCategoryCode": str(display_cat),
                "displayCategoryName": display_cat_name,
            },
            "raw": raw,
        }

    @staticmethod
    def _get_public_ip() -> str:
        try:
            return httpx.get("https://api.ipify.org", timeout=5).text.strip()
        except Exception:
            return "확인불가"

    def get_orders(self, status: str = "ACCEPT", hours_back: int = 2, limit: int = 100) -> list[dict]:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        from_dt = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%S")
        to_dt = now.strftime("%Y-%m-%dT%H:%M:%S")
        path = (
            f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/ordersheets"
            f"?createdAtFrom={from_dt}&createdAtTo={to_dt}&status={status}&perPage={limit}"
        )
        try:
            r = self._get(path)
            if r.status_code == 200:
                data = r.json(); sheets = data.get("data", []) or []; results = []
                for sheet in (sheets if isinstance(sheets, list) else []):
                    order_id = str(sheet.get("orderId", "")); buyer = sheet.get("buyer", {}) or {}; receiver = sheet.get("receiver", {}) or {}
                    for item in sheet.get("orderItems", []):
                        results.append({
                            "orderId": order_id, "orderItemId": str(item.get("orderItemId", "")), "vendorItemId": str(item.get("vendorItemId", "")),
                            "productName": item.get("productName", ""), "quantity": int(item.get("shippingCount", 1)), "salesPrice": float(item.get("salesPrice", 0)),
                            "buyerName": buyer.get("name", ""), "receiverName": receiver.get("name", ""),
                            "receiverAddr": (receiver.get("addr1", "") + " " + receiver.get("addr2", "")).strip(),
                            "receiverPhone": receiver.get("phone1", "") or receiver.get("safeNumber", ""),
                            "shippingMessage": receiver.get("shippingMessage", ""), "orderedAt": sheet.get("orderedAt", ""),
                        })
                return results
            logger.warning("쿠팡 주문 수집 HTTP %s: %s", r.status_code, r.text[:200])
        except Exception as exc:
            logger.error("쿠팡 주문 수집 실패: %s", exc)
        return []

    def register_shipment(self, order_id: str, order_item_id: str, delivery_company: str, invoice_number: str) -> dict:
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/orders/{order_id}/orderItems/{order_item_id}/shipments"
        try:
            r = self._post(path, {"deliveryCompanyCode": delivery_company, "invoiceNumber": invoice_number})
            if r.status_code in (200, 201): return {"ok": True, "data": r.json()}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as exc: return {"ok": False, "error": str(exc)}

    def update_vendor_item_stock(self, vendor_item_id: str, qty: int) -> dict:
        path = f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}"
        try:
            r = httpx.patch(f"{API}{path}", headers=self._sign("PATCH", urlparse(path).path, ""), json={"maximumBuyCount": 99, "stockQuantity": qty}, timeout=15)
            return {"ok": True} if r.status_code in (200, 201) else {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as exc: return {"ok": False, "error": str(exc)}

    def update_product_price(self, vendor_item_id: str, price: int) -> dict:
        path = f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}"
        try:
            r = httpx.patch(f"{API}{path}", headers=self._sign("PATCH", urlparse(path).path, ""), json={"salePrice": price, "originalPrice": price}, timeout=15)
            return {"ok": True} if r.status_code in (200, 201) else {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as exc: return {"ok": False, "error": str(exc)}

    def get_seller_product(self, seller_product_id: str) -> dict:
        path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{seller_product_id}"
        r = self._get(path)
        if r.status_code != 200:
            raise ValueError(f"쿠팡 상품조회 실패 HTTP {r.status_code}: {r.text[:300]}")
        return r.json().get("data", {})

    def list_seller_products(self, status: str = "", max_pages: int = 20, page_size: int = 50) -> list[dict]:
        results: list[dict] = []; next_token = ""
        for _ in range(max_pages):
            query = f"vendorId={self._vendor_id}&maxPerPage={page_size}"
            if status: query += f"&status={status}"
            if next_token: query += f"&nextToken={next_token}"
            r = self._get(f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products?{query}")
            if r.status_code != 200: raise ValueError(f"쿠팡 상품목록 조회 실패 HTTP {r.status_code}: {r.text[:300]}")
            data = r.json(); page_items = data.get("data", []) or []; results.extend(page_items); next_token = data.get("nextToken", "") or ""
            if not next_token or not page_items: break
        return results

    def update_seller_product(self, seller_product_id: str, name: str | None = None, detail_html: str | None = None) -> dict:
        try:
            current = self.get_seller_product(seller_product_id)
        except Exception as exc:
            return {"ok": False, "error": f"현재 상품 조회 실패: {exc}"}
        if name:
            current["sellerProductName"] = name[:100]; current["displayProductName"] = name[:100]
            for item in current.get("items", []): item["itemName"] = name[:150]
        if detail_html:
            for item in current.get("items", []):
                item["contents"] = [{"contentsType": "HTML", "contentDetails": [{"content": detail_html[:50000], "detailType": "TEXT"}]}]
        try:
            r = self._put("/v2/providers/seller_api/apis/api/v1/marketplace/seller-products", current)
            if r.status_code in (200, 201): return {"ok": True}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        except Exception as exc: return {"ok": False, "error": str(exc)}


_uploader: CoupangUploader | None = None


def get_coupang_uploader() -> CoupangUploader:
    global _uploader
    if _uploader is None:
        _uploader = CoupangUploader()
    return _uploader


def reset_coupang_uploader() -> None:
    global _uploader
    _uploader = None
