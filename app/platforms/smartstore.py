"""네이버 스마트스토어 Commerce API 업로더.

인증: bcrypt 서명 (client_id + timestamp → bcrypt hash → base64)
이미지: 외부 URL 다운로드 → Naver CDN 업로드 (/v1/product-images/upload)
"""
from __future__ import annotations
import base64
import io
import logging
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)
API = "https://api.commerce.naver.com/external"

ORIGIN_CODES = {
    "중국": "0200037", "일본": "0200036", "미국": "0204000",
    "베트남": "0200014", "한국": "0100000", "기타해외": "0200000",
    "인도네시아": "0200013", "태국": "0200015", "홍콩": "0200035",
    "대만": "0200038", "캐나다": "0204001", "영국": "0203001",
    "독일": "0203002", "프랑스": "0203003", "이탈리아": "0203004",
}

CATEGORY_MAP = {
    # 여성의류
    "러닝/캐미솔": "50000803", "이너웨어": "50000803",
    "티셔츠": "50000803", "여성의류": "50000803",
    "의류": "50000803", "패션": "50000803",
    "홈웨어": "50000803", "잠옷": "50000803",
    "원피스": "50000803", "블라우스": "50000803",
    "레깅스": "50000803", "바지": "50000803",
    # 스포츠/레저
    "스포츠": "50005505",
    # 생활/가전
    "생활": "50005804", "주방": "50001966",
    # 뷰티
    "뷰티": "50000140", "화장품": "50000140",
    # 식품
    "식품": "50000641",
}

# 스마트스토어 금지 문자: 콤마·슬래시·특수기호 일부
_SS_FORBIDDEN = str.maketrans({",": " ", "/": " ", "|": " ", ";": " ", '"': "", "'": ""})


def _clean_option_value(v: str) -> str:
    """스마트스토어 옵션값 금지 문자를 제거하고 50자로 자른다."""
    cleaned = str(v).translate(_SS_FORBIDDEN).strip()
    # 연속 공백 정리
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    return cleaned[:50]


class SmartStoreUploader:
    def __init__(self):
        s = get_settings()
        # strip() — .env 값에 개행·공백 포함 시 인증 오류 방지
        self._client_id = s.naver_client_id.strip()
        self._client_secret = s.naver_client_secret.strip()
        self._after_service_phone = (s.naver_after_service_phone or "010-0000-0000").strip()
        self._delivery_code = (s.naver_delivery_company_code or "CJGLS").strip()
        self._access_token = ""
        self._token_exp = 0.0
        self._shipping_id: int | None = None
        self._return_id: int | None = None
        self._addr_fetched = False

    # ── 인증 ─────────────────────────────────────────────────────────────────

    def _ensure_token(self) -> None:
        if time.time() < self._token_exp - 60:
            return
        import bcrypt
        secret = self._client_secret
        # docker-compose $$2a$$ 이중 이스케이프 처리
        if secret.startswith("$$"):
            secret = secret.replace("$$", "$")
        ts = str(int(time.time() * 1000))
        pw = f"{self._client_id}_{ts}"
        hashed = bcrypt.hashpw(pw.encode(), secret.encode())
        sign = base64.b64encode(hashed).decode()
        r = httpx.post(
            f"{API}/v1/oauth2/token",
            data={"grant_type": "client_credentials", "client_id": self._client_id,
                  "timestamp": ts, "client_secret_sign": sign, "type": "SELF"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        self._access_token = data["access_token"]
        self._token_exp = time.time() + data.get("expires_in", 3600)

    def _headers(self) -> dict:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json;charset=UTF-8"}

    def _auth_header(self) -> dict:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    # ── 주소 ID 자동 조회 ────────────────────────────────────────────────────

    def _ensure_addresses(self) -> None:
        if self._addr_fetched:
            return
        self._addr_fetched = True
        self._ensure_token()
        for path, attr in [("/v2/seller/shipping-addresses", "_shipping_id"),
                            ("/v2/seller/return-addresses", "_return_id")]:
            try:
                r = httpx.get(f"{API}{path}", headers=self._auth_header(), timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    items = (data if isinstance(data, list)
                             else data.get("shippingAddresses")
                             or data.get("returnAddresses") or [])
                    for item in (items if isinstance(items, list) else []):
                        if item.get("defaultYn") == "Y" or item.get("isDefault"):
                            addr_id = item.get("addressNo") or item.get("id")
                            if addr_id:
                                setattr(self, attr, int(addr_id))
                                break
                    if not getattr(self, attr) and isinstance(items, list) and items:
                        addr_id = items[0].get("addressNo") or items[0].get("id")
                        if addr_id:
                            setattr(self, attr, int(addr_id))
            except Exception as e:
                logger.debug("주소 조회 실패 (생략): %s", e)

    # ── 이미지 업로드 → Naver CDN ────────────────────────────────────────────

    def _upload_image(self, url: str) -> str:
        """외부 URL → Naver CDN URL. 실패 시 빈 문자열."""
        if url.startswith("https://shop-phinf.pstatic.net"):
            return url
        try:
            r = httpx.get(url, timeout=15, follow_redirects=True)
            r.raise_for_status()
            img_bytes = r.content
            ct = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            ext = "jpg" if "jpeg" in ct else ct.split("/")[-1]
        except Exception as e:
            logger.warning("이미지 다운로드 실패 [%s]: %s", url, e)
            return ""

        self._ensure_token()
        try:
            resp = httpx.post(
                f"{API}/v1/product-images/upload",
                headers=self._auth_header(),
                files={"imageFiles": (f"img.{ext}", io.BytesIO(img_bytes), ct)},
                timeout=30,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                cdn = (data.get("images") or [{}])[0].get("url") or data.get("url", "")
                if cdn:
                    return cdn
            logger.warning("스마트스토어 이미지 업로드 실패 %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("스마트스토어 이미지 업로드 예외: %s", e)
        return ""

    def _prepare_images(self, urls: list[str], max_count: int = 5) -> list[str]:
        result = []
        for url in urls[:max_count]:
            if not url:
                continue
            cdn = self._upload_image(url)
            if cdn:
                result.append(cdn)
            time.sleep(0.3)
        return result

    # ── 상품 등록 ────────────────────────────────────────────────────────────

    @retry(retry=retry_if_exception_type(httpx.HTTPError),
           stop=stop_after_attempt(2), wait=wait_exponential(min=3, max=15))
    def create_product(self, product: dict) -> dict:
        self._ensure_addresses()

        rep_images = self._prepare_images(product.get("images", [])[:5])
        detail_images = self._prepare_images(product.get("detail_images", [])[:10])

        if not rep_images:
            raise ValueError(
                "스마트스토어: 대표 이미지 CDN 업로드 실패\n"
                "IMAGE API 권한이 필요합니다. 네이버 판매자센터 > API 관리 > 권한 신청"
            )

        detail_html = product.get("detail_html", "")
        if detail_images:
            img_block = "\n".join(
                f'<img src="{u}" style="max-width:860px;display:block;margin:0 auto 4px;">'
                for u in detail_images
            )
            detail_html = img_block + ("\n" + detail_html if detail_html else "")
        if not detail_html:
            detail_html = f"<p>{product['name']}</p>"

        cat_raw = product.get("category", "")
        category_id = next((v for k, v in CATEGORY_MAP.items() if k in cat_raw), "50000803")

        origin_raw = product.get("origin", "중국")
        area_code = ORIGIN_CODES.get(origin_raw, "0200037")

        shipping_fee = int(product.get("shipping_fee", 3000))
        fee_type = "FREE" if shipping_fee == 0 else "PAID"

        options_raw = product.get("options", [])
        option_payload = self._build_options(options_raw, product.get("stock", 999))

        brand = product.get("brand") or "수입산"
        payload: dict[str, Any] = {
            "originProduct": {
                "statusType": "SALE",
                "saleType": "NEW",
                "leafCategoryId": category_id,
                "name": product["name"][:100],
                "images": {
                    "representativeImage": {"url": rep_images[0]},
                    "optionalImages": [{"url": u} for u in rep_images[1:]],
                },
                "detailContent": detail_html,
                "salePrice": (int(product["sell_price"]) // 10) * 10 or 10,
                "stockQuantity": product.get("stock", 999),
                "deliveryInfo": {
                    "deliveryType": "DELIVERY",
                    "deliveryAttributeType": "NORMAL",
                    "deliveryCompany": self._delivery_code,
                    "deliveryFee": {
                        "deliveryFeeType": fee_type,
                        # PREPAID(선결제): 구매자가 주문 시 결제 — 일반 온라인 쇼핑 표준
                        # COLLECT(착불): 택배기사에게 직접 현금 납부 — 온라인 쇼핑에 부적합
                        **({"baseFee": shipping_fee or 2500, "deliveryFeePayType": "PREPAID"} if fee_type != "FREE" else {}),
                    },
                    "claimDeliveryInfo": {
                        "returnDeliveryCompanyPriorityType": "PRIMARY",
                        "returnDeliveryFee": int(product.get("return_fee", 3000)),
                        "exchangeDeliveryFee": int(product.get("return_fee", 3000)),
                        **({"shippingAddressId": self._shipping_id} if self._shipping_id else {}),
                        **({"returnAddressId": self._return_id} if self._return_id else {}),
                    },
                },
                "detailAttribute": {
                    "naverShoppingSearchInfo": {
                        "modelName": product.get("sku", ""),
                        "manufacturerName": brand,
                        "brandName": brand,
                        # 카탈로그 매칭 자동연결 비활성화 (직접 등록 상품)
                        "catalogMatchingYn": "N",
                    },
                    "afterServiceInfo": {
                        "afterServiceTelephoneNumber": self._after_service_phone,
                        "afterServiceGuideContent": "상품 관련 문의는 고객센터로 연락 주세요.",
                    },
                    "originAreaInfo": {
                        "originAreaCode": area_code,
                        "content": origin_raw,
                        "importer": "수입사 미상",
                        "plural": False,
                    },
                    "taxType": "TAX",
                    "minorPurchasable": True,
                    "productInfoProvidedNotice": {
                        "productInfoProvidedNoticeType": "ETC",
                        "etc": {
                            "returnCostReason": "상품 이상 시 환불",
                            "noRefundReason": "변심 반품 불가 (상품 특성상)",
                            "qualityAssuranceStandard": "제조사 기준",
                            "compensationProcedure": "고객센터 접수",
                            "troubleShootingContents": "고객센터 문의",
                            "itemName": product["name"][:50],
                            "modelName": product.get("sku", ""),
                            "certificateDetails": "해당없음",
                            "manufacturer": brand,
                            "afterServiceDirector": self._after_service_phone,
                        },
                    },
                    **({"optionInfo": option_payload} if option_payload else {}),
                },
            },
            "smartstoreChannelProduct": {
                "naverShoppingRegistration": True,
                "channelProductDisplayStatusType": "ON",
            },
        }

        r = httpx.post(f"{API}/v2/products", headers=self._headers(), json=payload, timeout=60)
        if r.status_code not in (200, 201):
            raise ValueError(f"SmartStore API {r.status_code}: {r.text[:300]}")
        return r.json()

    @staticmethod
    def _build_options(options_raw: list[dict], stock: int) -> dict | None:
        if not options_raw:
            return None
        groups: dict[str, Any] = {}
        values_list = [opt.get("values", []) for opt in options_raw[:2]]
        for i, opt in enumerate(options_raw[:2]):
            groups[f"optionGroupName{i+1}"] = opt.get("name", f"옵션{i+1}")

        combinations: list[dict] = []
        if len(values_list) == 1:
            for v in values_list[0]:
                clean_v = _clean_option_value(v)
                if not clean_v:
                    continue
                combinations.append({
                    "stockQuantity": max(1, stock // max(len(values_list[0]), 1)),
                    "price": 0, "usable": True, "optionName1": clean_v,
                })
        elif len(values_list) == 2:
            for v1 in values_list[0]:
                for v2 in values_list[1]:
                    cv1, cv2 = _clean_option_value(v1), _clean_option_value(v2)
                    if not cv1 or not cv2:
                        continue
                    n = max(len(values_list[0]) * len(values_list[1]), 1)
                    combinations.append({
                        "stockQuantity": max(1, stock // n),
                        "price": 0, "usable": True, "optionName1": cv1, "optionName2": cv2,
                    })
        if not combinations:
            return None
        return {
            "optionCombinationSortType": "CREATE",
            "optionCombinationGroupNames": groups,
            "optionCombinations": combinations,
            "useStockManagement": True,
        }


    # ── 주문 수집 ────────────────────────────────────────────────────────────

    def get_orders(self, from_date: str = "", to_date: str = "",
                   pay_status: str = "PAYMENT_DONE", limit: int = 100) -> list[dict]:
        """스마트스토어 주문 목록 수집.

        from_date / to_date: yyyyMMdd (없으면 오늘 기준 최근 2일)
        pay_status: PAYMENT_DONE | PAYED | DELIVERY_STANDBY | DELIVERING 등
        Returns: [{orderId, productOrderId, originProductNo, productName, quantity,
                   unitPrice, buyerName, receiverName, receiverAddr, receiverPhone,
                   orderedAt, shippingMessage}]
        """
        if not from_date or not to_date:
            from datetime import datetime, timedelta
            now = datetime.now()
            from_date = (now - timedelta(days=2)).strftime("%Y%m%d")
            to_date = now.strftime("%Y%m%d")

        self._ensure_token()
        params = {
            "dispatchFrom": from_date,
            "dispatchTo": to_date,
            "paymentDateType": "PAY_DATE",
            "payStatus": pay_status,
            "page": 1,
            "size": limit,
        }
        try:
            r = __import__("httpx").get(
                f"{API}/v1/pay-order/vendor/orders",
                params=params,
                headers=self._headers(),
                timeout=20,
            )
            if r.status_code == 200:
                data = r.json()
                orders_raw = data.get("data", {}).get("contents", []) or data.get("contents", [])
                results = []
                for order in (orders_raw if isinstance(orders_raw, list) else []):
                    order_id = str(order.get("orderId", ""))
                    for po in order.get("productOrders", []):
                        results.append({
                            "orderId": order_id,
                            "productOrderId": str(po.get("productOrderId", "")),
                            "originProductNo": str(po.get("product", {}).get("originProductNo", "")),
                            "productName": po.get("product", {}).get("name", ""),
                            "quantity": int(po.get("quantity", 1)),
                            "unitPrice": float(po.get("unitPrice", 0)),
                            "buyerName": order.get("orderer", {}).get("name", ""),
                            "receiverName": order.get("deliveryAddress", {}).get("name", ""),
                            "receiverAddr": (
                                order.get("deliveryAddress", {}).get("roadAddress", "")
                                + " "
                                + order.get("deliveryAddress", {}).get("detailAddress", "")
                            ).strip(),
                            "receiverPhone": order.get("deliveryAddress", {}).get("tel1", ""),
                            "shippingMessage": order.get("deliveryAddress", {}).get("message", ""),
                            "orderedAt": order.get("paymentDate", ""),
                        })
                return results
            logger.warning("스마트스토어 주문 수집 HTTP %s: %s", r.status_code, r.text[:200])
        except Exception as exc:
            logger.error("스마트스토어 주문 수집 실패: %s", exc)
        return []

    def dispatch_product_order(self, product_order_id: str,
                               delivery_company: str, tracking_number: str) -> dict:
        """스마트스토어 발송 처리 (운송장 등록).

        delivery_company: CJGLS | LOGEN | KDEXP | HANJIN | POST 등
        """
        self._ensure_token()
        body = {
            "dispatchProductOrders": [{
                "productOrderId": product_order_id,
                "deliveryMethod": "PARCEL",
                "deliveryCompanyCode": delivery_company,
                "trackingNumber": tracking_number,
                "dispatchDate": __import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            }]
        }
        try:
            r = __import__("httpx").post(
                f"{API}/v1/pay-order/vendor/product-orders/dispatch",
                headers=self._headers(),
                json=body,
                timeout=20,
            )
            if r.status_code in (200, 201):
                return {"ok": True, "data": r.json()}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def update_stock(self, origin_product_no: str, channel_product_no: str,
                     qty: int) -> dict:
        """스마트스토어 재고 수량 업데이트.

        PUT /v2/products/{originProductNo}의 stockQuantity 필드를 업데이트.
        """
        self._ensure_token()
        try:
            # 먼저 현재 상품 정보 조회
            r_get = __import__("httpx").get(
                f"{API}/v2/products/{origin_product_no}",
                headers=self._headers(),
                timeout=15,
            )
            if r_get.status_code != 200:
                return {"ok": False, "error": f"상품 조회 실패 HTTP {r_get.status_code}"}

            payload = r_get.json()
            origin = payload.get("originProduct", {})
            origin["stockQuantity"] = qty

            r_put = __import__("httpx").put(
                f"{API}/v2/products/{origin_product_no}",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            if r_put.status_code in (200, 201):
                return {"ok": True}
            return {"ok": False, "error": f"HTTP {r_put.status_code}: {r_put.text[:200]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def update_price(self, origin_product_no: str, price: int) -> dict:
        """스마트스토어 판매가 업데이트."""
        self._ensure_token()
        try:
            r_get = __import__("httpx").get(
                f"{API}/v2/products/{origin_product_no}",
                headers=self._headers(), timeout=15,
            )
            if r_get.status_code != 200:
                return {"ok": False, "error": f"상품 조회 실패 HTTP {r_get.status_code}"}

            payload = r_get.json()
            payload["originProduct"]["salePrice"] = (price // 10) * 10 or 10

            r_put = __import__("httpx").put(
                f"{API}/v2/products/{origin_product_no}",
                headers=self._headers(), json=payload, timeout=30,
            )
            if r_put.status_code in (200, 201):
                return {"ok": True}
            return {"ok": False, "error": f"HTTP {r_put.status_code}: {r_put.text[:200]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def update_product_content(self, origin_product_no: str, name: str | None = None,
                               detail_html: str | None = None) -> dict:
        """스마트스토어 상품명/상세설명 업데이트 (SEO 반영).

        PUT /v2/products/{originProductNo}의 name/detailContent 필드만 교체하고
        나머지 필드는 조회한 그대로 유지한다 (update_stock/update_price와 동일한
        GET → 부분 수정 → PUT 패턴).
        """
        self._ensure_token()
        try:
            r_get = httpx.get(
                f"{API}/v2/products/{origin_product_no}",
                headers=self._headers(), timeout=15,
            )
            if r_get.status_code != 200:
                return {"ok": False, "error": f"상품 조회 실패 HTTP {r_get.status_code}"}

            payload = r_get.json()
            origin = payload.get("originProduct", {})
            if name:
                origin["name"] = name[:100]
            if detail_html:
                origin["detailContent"] = detail_html

            r_put = httpx.put(
                f"{API}/v2/products/{origin_product_no}",
                headers=self._headers(), json=payload, timeout=30,
            )
            if r_put.status_code in (200, 201):
                return {"ok": True}
            return {"ok": False, "error": f"HTTP {r_put.status_code}: {r_put.text[:200]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def list_origin_products(self, max_pages: int = 20, page_size: int = 50) -> list[dict]:
        """[실험적 — 실제 계정 미검증] 등록된 원상품 목록을 페이지네이션 조회한다.

        이 코드베이스에서 한 번도 호출해본 적 없는 엔드포인트다. 응답 스키마가
        예상과 다르면 빈 리스트만 채워질 수 있으니, 실패/빈 결과 시 실제 응답을
        로그로 확인하고 파싱 로직을 조정할 것 (app/sync/catalog_sync.py에서 사용).
        """
        self._ensure_token()
        results: list[dict] = []
        for page in range(1, max_pages + 1):
            r = httpx.get(
                f"{API}/v2/products",
                headers=self._headers(),
                params={"page": page, "size": page_size},
                timeout=20,
            )
            if r.status_code != 200:
                raise ValueError(f"스마트스토어 상품목록 조회 실패 HTTP {r.status_code}: {r.text[:300]}")

            data = r.json()
            page_items = data.get("contents") or data.get("content") or []
            if not page_items:
                break

            for item in page_items:
                channel_products = item.get("channelProducts") or []
                origin = channel_products[0] if channel_products else item
                results.append({
                    "originProductNo": str(item.get("originProductNo") or origin.get("originProductNo") or ""),
                    "name": origin.get("name") or item.get("name", ""),
                    "salePrice": origin.get("salePrice") or item.get("salePrice", 0),
                })

            if len(page_items) < page_size:
                break
        return results


_uploader: SmartStoreUploader | None = None


def get_smartstore_uploader() -> SmartStoreUploader:
    global _uploader
    if _uploader is None:
        _uploader = SmartStoreUploader()
    return _uploader


def reset_smartstore_uploader() -> None:
    """설정 변경 후 업로더 싱글턴을 재생성하도록 강제한다."""
    global _uploader
    _uploader = None
