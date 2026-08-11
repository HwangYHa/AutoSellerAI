"""쿠팡 Wing API 업로더 (HMAC-SHA256 인증)."""
from __future__ import annotations

import hashlib, hmac, logging, time
from typing import Any
from urllib.parse import urlparse, urlencode

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
API = "https://api-gateway.coupang.com"

CATEGORY_MAP = {
    "의류": "56101", "패션": "56101", "티셔츠": "56101",
    "이너": "56101", "나시": "56101", "여성": "56101",
    "홈웨어": "56101", "잠옷": "56101", "레깅스": "56101",
    "원피스": "56101", "블라우스": "56101", "바지": "56101",
    "생활": "56137", "주방": "56148", "뷰티": "56120",
    "전자": "56109", "식품": "56128", "스포츠": "56141",
}

# 쿠팡 유효 택배사 코드 (CVS 등 비표준 코드 → CJGLS 폴백)
_VALID_DELIVERY_CODES = {
    "CJGLS", "LOGEN", "HANJIN", "KDEXP", "POST",
    "LOTTE", "ILYANG", "DAESIN", "CHUNIL", "REGISTPOST",
    "PANTOS", "GSI", "SLX", "EPOST",
}


def _normalize_delivery_code(code: str) -> str:
    """유효하지 않은 택배사 코드를 CJGLS로 폴백한다."""
    c = (code or "").strip().upper()
    return c if c in _VALID_DELIVERY_CODES else "CJGLS"


class CoupangUploader:
    def __init__(self):
        s = get_settings()
        # strip() — .env 값에 개행·공백 포함 시 HMAC 포맷 오류 방지
        self._access_key = s.coupang_access_key.strip()
        self._secret_key = s.coupang_secret_key.strip()
        self._vendor_id = s.coupang_vendor_id.strip()
        self._vendor_user_id = s.coupang_vendor_user_id.strip()
        # Wing API: outboundShippingPlaceCode / returnCenterCode 는 long(정수) 타입
        self._outbound_code = int(str(s.coupang_outbound_shipping_place_code).strip())
        self._debug_credentials()
        self._return_code = int(s.coupang_return_center_code.strip())
        self._return_zip = s.coupang_return_zip_code.strip()
        self._return_addr = s.coupang_return_address.strip()
        self._return_addr_detail = s.coupang_return_address_detail.strip()
        self._contact = s.coupang_company_contact_number.strip()
        self._return_charge = s.coupang_return_charge
        # CVS 등 비표준 코드 입력 시 CJGLS(CJ대한통운)으로 폴백
        self._delivery_code = _normalize_delivery_code(
            s.coupang_delivery_company_code or "CJGLS"
        )

    # ── 자격증명 진단 ──────────────────────────────────────────────────────────

    def _debug_credentials(self) -> None:
        """초기화 시 키 형식 이상 여부를 로그에 출력 (실제 값은 노출하지 않음)."""
        issues = []
        if not self._access_key:
            issues.append("COUPANG_ACCESS_KEY 미설정")
        elif " " in self._access_key or "\t" in self._access_key:
            issues.append(f"COUPANG_ACCESS_KEY에 공백 포함 (len={len(self._access_key)})")
        if not self._secret_key:
            issues.append("COUPANG_SECRET_KEY 미설정")
        elif " " in self._secret_key or "\t" in self._secret_key:
            issues.append(f"COUPANG_SECRET_KEY에 공백 포함 (len={len(self._secret_key)})")
        if not self._vendor_id:
            issues.append("COUPANG_VENDOR_ID 미설정")
        elif not self._vendor_id.startswith("A"):
            issues.append(f"COUPANG_VENDOR_ID가 'A'로 시작하지 않음: '{self._vendor_id[:4]}...'")
        if issues:
            logger.warning("쿠팡 자격증명 문제 감지: %s", " / ".join(issues))
        else:
            logger.debug(
                "쿠팡 키 확인 — access_key: %s... (len=%d), vendor_id: %s",
                self._access_key[:4], len(self._access_key), self._vendor_id,
            )

    # ── 인증 ─────────────────────────────────────────────────────────────────

    def _sign(self, method: str, path: str, query: str = "") -> dict:
        if not self._access_key or not self._secret_key:
            raise ValueError(
                "쿠팡 API 키 미설정\n"
                "설정 > API 연동 > 쿠팡 Access Key / Secret Key를 입력하세요."
            )
        # Wing API는 signed-date를 'yyMMdd'T'HHmmss'Z'(GMT) 형식 문자열로 요구한다.
        # 이전 코드는 epoch 밀리초를 넣어 매번 "HMAC format is invalid" 401을 유발했다.
        datetime_gmt = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
        message = datetime_gmt + method.upper() + path + query
        sig = hmac.new(
            self._secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        auth = (f"CEA algorithm=HmacSHA256, access-key={self._access_key}, "
                f"signed-date={datetime_gmt}, signature={sig}")
        return {"Authorization": auth, "Content-Type": "application/json;charset=UTF-8"}

    def _get(self, path: str) -> httpx.Response:
        parsed = urlparse(path)
        # query 앞에 "?" 포함하지 않음 — HMAC 메시지에 raw query만 포함
        headers = self._sign("GET", parsed.path, parsed.query)
        return httpx.get(f"{API}{path}", headers=headers, timeout=15)

    def _post(self, path: str, body: dict) -> httpx.Response:
        # POST는 query string 없음 — path에 "?" 있으면 path만 추출
        clean_path = urlparse(path).path
        headers = self._sign("POST", clean_path, "")
        return httpx.post(f"{API}{path}", headers=headers, json=body, timeout=30)

    # ── 상품 등록 ────────────────────────────────────────────────────────────

    def create_product(self, product: dict) -> dict:
        """상품 등록. 성공 시 {"productId": ..., "sellerProductId": ...} 반환."""
        cat_raw = product.get("category", "")
        display_cat = "56101"
        for key, val in CATEGORY_MAP.items():
            if key in cat_raw:
                display_cat = val
                break

        images = [u for u in product.get("images", []) if u and u.startswith("http")]
        detail_images = [u for u in product.get("detail_images", []) if u and u.startswith("http")]

        if not images:
            raise ValueError("쿠팡: 이미지 없음 (최소 1장 필요)")

        # images: 대표(REPRESENTATION) + 추가(DETAIL)
        img_list = [
            {"imageOrder": i, "imageType": "REPRESENTATION" if i == 0 else "DETAIL", "vendorPath": u}
            for i, u in enumerate(images[:5])
        ]

        # contents: 상세 이미지 우선 → 일반 이미지 → HTML
        contents: list[dict] = []
        for u in (detail_images or images):
            contents.append({"contentsType": "IMAGE_NO_SPACE",
                              "contentDetails": [{"content": u, "detailType": "IMAGE"}]})
        if product.get("detail_html"):
            contents.append({"contentsType": "HTML",
                              "contentDetails": [{"content": product["detail_html"][:50000], "detailType": "TEXT"}]})

        # 고시정보
        brand = product.get("brand") or "수입산"
        notices = [
            {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "품명 및 모델명",
             "content": f"{brand} {product.get('sku','')}".strip()[:40] or product["name"][:40]},
            {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "인증/허가 사항", "content": "해당없음"},
            {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제조국(원산지)",
             "content": product.get("origin", "중국")},
            {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제조자(수입자)", "content": brand},
            {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "소비자상담 관련 전화번호",
             "content": self._contact or "02-0000-0000"},
        ]

        options_raw = product.get("options", [])
        items = self._build_items(product, options_raw, img_list)

        shipping_fee = int(product.get("shipping_fee", 3000))
        # Wing API: deliveryChargeType 은 실제 배송비에 따라 분기해야 함
        #   FREE (무료), NOT_FREE (유료), CONDITIONAL_FREE (조건부 무료)
        if shipping_fee == 0:
            delivery_charge_type = "FREE"
        else:
            delivery_charge_type = "NOT_FREE"

        # 우체국(POST): 제주/도서산간 추가배송비 0원만 허용
        # 그 외 택배사: 일반 추가배송비 적용 (제주 3000, 도서산간 5000)
        if self._delivery_code == "POST":
            jeju_fee, island_fee = 0, 0
        else:
            jeju_fee, island_fee = 3000, 5000

        body: dict[str, Any] = {
            "displayCategoryCode": display_cat,
            "sellerProductName": product["name"][:200],
            "vendorId": self._vendor_id,
            "saleStartedAt": "2020-01-01T00:00:00",
            "saleEndedAt": "2099-12-31T23:59:59",
            "displayProductName": product["name"][:200],
            "brand": brand,
            "generalProductFlag": True,
            "outboundShippingPlaceCode": self._outbound_code,
            "shippingType": "VENDOR_DIRECT",
            "remoteAreaCode": "NONE",
            "freeShipOverAmount": 0,
            "deliveryChargeType": delivery_charge_type,
            "deliveryCharge": shipping_fee,
            "additionalShippingFeeByArea": {
                "deliveryFeeByJeju": jeju_fee,
                "deliveryFeeByEtcArea": island_fee,
            },
            "returnChargeVendor": int(self._return_charge),
            "returnCharge": int(self._return_charge),
            "returnCenterCode": self._return_code,
            "returnAddress": {
                "returnZipCode": self._return_zip,
                "returnAddress": self._return_addr,
                "returnAddressDetail": self._return_addr_detail,
            },
            "productNotices": notices,
            "items": items,
            "contents": contents,
        }

        path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
        r = self._post(path, body)
        if r.status_code == 403:
            ip = self._get_public_ip()
            raise ValueError(
                f"쿠팡 IP 미화이트리스트 (서버 IP: {ip})\n"
                f"openapisupport@coupang.com 으로 화이트리스트 등록 요청 필요"
            )
        if r.status_code not in (200, 201):
            raise ValueError(f"쿠팡 API {r.status_code}: {r.text[:300]}")
        return r.json()

    @staticmethod
    def _build_items(product: dict, options_raw: list[dict], img_list: list) -> list[dict]:
        price = int(product["sell_price"])
        stock = int(product.get("stock", 999))
        brand = product.get("brand") or "수입산"

        base_item: dict[str, Any] = {
            "itemName": product["name"][:200],
            "originalPrice": price,
            "salePrice": price,
            "maximumBuyCount": 99,
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
            "notices": [],
            "certifications": [],
            "attributes": [{"attributeTypeName": "브랜드", "attributeValueName": brand}],
        }

        if not options_raw:
            return [{**base_item, "vendorItemName": product["name"][:100],
                     "stockQuantity": stock, "offerCondition": "NEW", "offerDescription": ""}]

        items = []
        opt = options_raw[0]
        values = opt.get("values", [])
        per = max(1, stock // len(values)) if values else stock
        for v in values:
            items.append({
                **base_item,
                "vendorItemName": f"{product['name'][:80]} - {v}",
                "stockQuantity": per,
                "offerCondition": "NEW",
                "offerDescription": "",
                "attributes": [
                    {"attributeTypeName": "브랜드", "attributeValueName": brand},
                    {"attributeTypeName": opt.get("name", "옵션"), "attributeValueName": v},
                ],
            })
        return items

    @staticmethod
    def _get_public_ip() -> str:
        try:
            return httpx.get("https://api.ipify.org", timeout=5).text.strip()
        except Exception:
            return "확인불가"


    # ── 주문 수집 ────────────────────────────────────────────────────────────

    def get_orders(self, status: str = "ACCEPT",
                   hours_back: int = 2, limit: int = 100) -> list[dict]:
        """쿠팡 주문 목록 수집.

        status: ACCEPT | INSTRUCT | DEPARTURE | DELIVERING | FINAL_DELIVERY
        Returns: [{orderId, orderItemId, vendorItemId, productName, quantity,
                   salesPrice, buyerName, receiverName, receiverAddr,
                   receiverPhone, orderedAt, shippingMessage}]
        """
        from datetime import datetime, timezone, timedelta
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
                data = r.json()
                sheets = data.get("data", []) or []
                results = []
                for sheet in (sheets if isinstance(sheets, list) else []):
                    order_id = str(sheet.get("orderId", ""))
                    buyer = sheet.get("buyer", {}) or {}
                    receiver = sheet.get("receiver", {}) or {}
                    for item in sheet.get("orderItems", []):
                        results.append({
                            "orderId": order_id,
                            "orderItemId": str(item.get("orderItemId", "")),
                            "vendorItemId": str(item.get("vendorItemId", "")),
                            "productName": item.get("productName", ""),
                            "quantity": int(item.get("shippingCount", 1)),
                            "salesPrice": float(item.get("salesPrice", 0)),
                            "buyerName": buyer.get("name", ""),
                            "receiverName": receiver.get("name", ""),
                            "receiverAddr": (
                                (receiver.get("addr1", "") + " " + receiver.get("addr2", "")).strip()
                            ),
                            "receiverPhone": receiver.get("phone1", "") or receiver.get("safeNumber", ""),
                            "shippingMessage": receiver.get("shippingMessage", ""),
                            "orderedAt": sheet.get("orderedAt", ""),
                        })
                return results
            logger.warning("쿠팡 주문 수집 HTTP %s: %s", r.status_code, r.text[:200])
        except Exception as exc:
            logger.error("쿠팡 주문 수집 실패: %s", exc)
        return []

    def register_shipment(self, order_id: str, order_item_id: str,
                          delivery_company: str, invoice_number: str) -> dict:
        """쿠팡에 운송장 번호를 등록한다 (발송처리).

        delivery_company: CJGLS | LOGEN | KDEXP | HANJIN | POST 등
        """
        path = (
            f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}"
            f"/orders/{order_id}/orderItems/{order_item_id}/shipments"
        )
        body = {
            "deliveryCompanyCode": delivery_company,
            "invoiceNumber": invoice_number,
        }
        try:
            r = self._post(path, body)
            if r.status_code in (200, 201):
                return {"ok": True, "data": r.json()}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def update_vendor_item_stock(self, vendor_item_id: str, qty: int) -> dict:
        """쿠팡 vendorItem 재고를 업데이트한다."""
        path = (
            f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}"
        )
        body = {"maximumBuyCount": 99, "stockQuantity": qty}
        try:
            headers = self._sign("PATCH", urlparse(path).path, "")
            r = __import__("httpx").patch(f"{API}{path}", headers=headers,
                                          json=body, timeout=15)
            if r.status_code in (200, 201):
                return {"ok": True}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def update_product_price(self, vendor_item_id: str, price: int) -> dict:
        """쿠팡 vendorItem 판매가를 업데이트한다."""
        path = (
            f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}"
        )
        body = {"salePrice": price, "originalPrice": price}
        try:
            from urllib.parse import urlparse
            headers = self._sign("PATCH", urlparse(path).path, "")
            r = __import__("httpx").patch(f"{API}{path}", headers=headers,
                                          json=body, timeout=15)
            if r.status_code in (200, 201):
                return {"ok": True}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _put(self, path: str, body: dict) -> httpx.Response:
        clean_path = urlparse(path).path
        headers = self._sign("PUT", clean_path, "")
        return httpx.put(f"{API}{path}", headers=headers, json=body, timeout=30)

    def get_seller_product(self, seller_product_id: str) -> dict:
        """등록된 판매상품 상세 조회 (상품수정 전 현재 상태 확인용)."""
        path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{seller_product_id}"
        r = self._get(path)
        if r.status_code != 200:
            raise ValueError(f"쿠팡 상품조회 실패 HTTP {r.status_code}: {r.text[:300]}")
        return r.json().get("data", {})

    def list_seller_products(self, status: str = "", max_pages: int = 20, page_size: int = 50) -> list[dict]:
        """등록된 판매상품 목록을 nextToken 페이지네이션으로 전체 조회한다.

        이 앱을 통하지 않고 Wing 판매자센터에서 직접 등록한 상품도 포함해
        전체 카탈로그를 가져올 수 있다 (app/sync/catalog_sync.py에서 사용).
        """
        results: list[dict] = []
        next_token = ""
        for _ in range(max_pages):
            query = f"vendorId={self._vendor_id}&maxPerPage={page_size}"
            if status:
                query += f"&status={status}"
            if next_token:
                query += f"&nextToken={next_token}"
            path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products?{query}"
            r = self._get(path)
            if r.status_code != 200:
                raise ValueError(f"쿠팡 상품목록 조회 실패 HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            page_items = data.get("data", []) or []
            results.extend(page_items)
            next_token = data.get("nextToken", "") or ""
            if not next_token or not page_items:
                break
        return results

    def update_seller_product(self, seller_product_id: str, name: str | None = None,
                              detail_html: str | None = None) -> dict:
        """[실험적 — 실제 계정 미검증] 등록된 판매상품의 상품명/상세설명을 수정한다.

        Wing Open API의 `PUT .../seller-products/{id}`는 create_product와 동일하게 상품
        전체 필드를 요구하므로, 먼저 현재 상태를 조회한 뒤 이름/콘텐츠 필드만 바꿔 그대로
        되돌려 보낸다. 카테고리·이미지 등 필드 변경 시 쿠팡 재승인 심사가 다시 걸릴 수 있고,
        GET 응답의 읽기전용 필드가 PUT에서 거부될 수 있다 — 적용 전 낮은 리스크 상품으로
        먼저 테스트할 것.
        """
        try:
            current = self.get_seller_product(seller_product_id)
        except Exception as exc:
            return {"ok": False, "error": f"현재 상품 조회 실패: {exc}"}

        if name:
            current["sellerProductName"] = name[:200]
            current["displayProductName"] = name[:200]
            for item in current.get("items", []):
                item["itemName"] = name[:200]
                # vendorItemName은 "상품명 - 옵션값" 형식이므로 옵션 접미사만 보존
                base = item.get("vendorItemName", "")
                suffix = base.split(" - ", 1)[1] if " - " in base else ""
                item["vendorItemName"] = f"{name[:80]} - {suffix}" if suffix else name[:100]

        if detail_html:
            contents = [c for c in current.get("contents", []) if c.get("contentsType") != "HTML"]
            contents.append({"contentsType": "HTML",
                             "contentDetails": [{"content": detail_html[:50000], "detailType": "TEXT"}]})
            current["contents"] = contents

        path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{seller_product_id}"
        try:
            r = self._put(path, current)
            if r.status_code in (200, 201):
                return {"ok": True}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


_uploader: CoupangUploader | None = None


def get_coupang_uploader() -> CoupangUploader:
    global _uploader
    if _uploader is None:
        _uploader = CoupangUploader()
    return _uploader


def reset_coupang_uploader() -> None:
    """설정 변경 후 업로더 싱글턴을 재생성하도록 강제한다."""
    global _uploader
    _uploader = None
