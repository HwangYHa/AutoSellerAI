"""Read/write adapters for marketplace SEO diagnostics.

Only public seller APIs that are directly relevant to product search quality are
used here.  Search impressions, clicks and live ranking are not invented when a
marketplace does not expose them through the seller API; the optimizer combines
these remote product facts with locally collected ProductPerformance/Order data.

Write policy is intentionally conservative:
- category, price and shipping are never changed by this module;
- only explicitly selected SEO fields are mutated;
- a fresh remote product is read immediately before every write so options and
  unrelated seller-managed fields are preserved.
"""
from __future__ import annotations

import copy
import logging
import re
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)
NAVER_API = "https://api.commerce.naver.com/external"

LOCKED_FIELDS = frozenset({"category", "price", "shipping", "images", "attributes"})
SEO_WRITE_FIELDS = frozenset({"title", "tags", "detail", "brand"})


def _response_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {}


def _clean_coupang_tags(tags: list[str]) -> list[str]:
    """Coupang: <=20 tags, <=20 chars each, de-duplicated and safe characters."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        text = re.sub(r"[^0-9A-Za-z가-힣\s!@#$%^&*+;:’.'_-]", " ", str(raw or ""))
        text = re.sub(r"\s+", " ", text).strip()[:20]
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
        if len(out) >= 20:
            break
    return out


def _clean_naver_tags(tags: list[Any]) -> list[dict[str, Any]]:
    """Normalize either strings or {code,text} objects to Naver sellerTags."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in tags:
        if isinstance(raw, dict):
            text = str(raw.get("text") or raw.get("name") or "").strip()
            code = raw.get("code")
        else:
            text = str(raw or "").strip()
            code = None
        text = re.sub(r"[^0-9A-Za-z가-힣\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        item: dict[str, Any] = {"text": text}
        if code not in (None, ""):
            try:
                item["code"] = int(code)
            except (TypeError, ValueError):
                pass
        out.append(item)
        if len(out) >= 10:  # SmartStore UI/SEO guide allows up to ten seller tags.
            break
    return out


class CoupangSeoApi:
    """SEO-relevant public Coupang Wing APIs."""

    def __init__(self, uploader=None):
        if uploader is None:
            from app.platforms.coupang import get_coupang_uploader
            uploader = get_coupang_uploader()
        self.uploader = uploader

    def list_products(self, *, max_pages: int = 50) -> list[dict]:
        return self.uploader.list_seller_products(max_pages=max_pages, page_size=100)

    def get_product(self, seller_product_id: str) -> dict:
        return self.uploader.get_seller_product(str(seller_product_id))

    def category_valid(self, display_category_code: str | int) -> tuple[bool | None, str]:
        code = str(display_category_code or "").strip()
        if not code:
            return None, "카테고리 코드 없음"
        path = f"/v2/providers/seller_api/apis/api/v1/marketplace/meta/display-categories/{code}/status"
        try:
            r = self.uploader._get(path)
            if r.status_code != 200:
                return None, f"HTTP {r.status_code}"
            payload = _response_json(r)
            return bool(payload.get("data")), "ok"
        except Exception as exc:
            return None, str(exc)

    def get_category_metadata(self, display_category_code: str | int) -> tuple[dict, str]:
        code = str(display_category_code or "").strip()
        if not code:
            return {}, "카테고리 코드 없음"
        path = (
            "/v2/providers/seller_api/apis/api/v1/marketplace/meta/"
            f"category-related-metas/display-category-codes/{code}"
        )
        try:
            r = self.uploader._get(path)
            if r.status_code != 200:
                return {}, f"HTTP {r.status_code}: {r.text[:240]}"
            payload = _response_json(r)
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, list):
                return (data[0] if data else {}), "ok"
            return (data if isinstance(data, dict) else {}), "ok"
        except Exception as exc:
            return {}, str(exc)

    def recommend_category(self, product: dict[str, Any]) -> tuple[dict, str]:
        try:
            code, name = self.uploader._recommend_category(product)
            return {"displayCategoryCode": str(code), "name": name}, "ok"
        except Exception as exc:
            return {}, str(exc)

    def get_histories(self, seller_product_id: str, max_pages: int = 5) -> tuple[list[dict], str]:
        results: list[dict] = []
        next_token = ""
        try:
            for _ in range(max_pages):
                query = "maxPerPage=50"
                if next_token:
                    query += f"&nextToken={next_token}"
                path = (
                    "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/"
                    f"{seller_product_id}/histories?{query}"
                )
                r = self.uploader._get(path)
                if r.status_code != 200:
                    return results, f"HTTP {r.status_code}: {r.text[:200]}"
                payload = _response_json(r)
                page = payload.get("data") or [] if isinstance(payload, dict) else []
                if isinstance(page, list):
                    results.extend(page)
                next_token = str(payload.get("nextToken") or "") if isinstance(payload, dict) else ""
                if not next_token or not page:
                    break
            return results, "ok"
        except Exception as exc:
            return results, str(exc)

    @staticmethod
    def current_fields(detail: dict) -> dict[str, Any]:
        items = detail.get("items") or []
        first = items[0] if items and isinstance(items[0], dict) else {}
        tags = detail.get("searchTags")
        if not isinstance(tags, list):
            tags = first.get("searchTags") if isinstance(first.get("searchTags"), list) else []
        attrs: list[dict] = []
        for item in items:
            for attr in item.get("attributes") or []:
                if isinstance(attr, dict):
                    attrs.append(attr)
        images = first.get("images") or []
        contents = first.get("contents") or []
        return {
            "title": str(detail.get("displayProductName") or detail.get("sellerProductName") or ""),
            "seller_product_name": str(detail.get("sellerProductName") or ""),
            "general_product_name": str(detail.get("generalProductName") or ""),
            "brand": str(detail.get("brand") or ""),
            "category": str(detail.get("displayCategoryCode") or ""),
            "tags": [str(x) for x in tags if str(x).strip()],
            "attributes": attrs,
            "images": images,
            "image_count": len(images),
            "detail_present": bool(contents),
            "detail": contents,
            "status": str(detail.get("statusName") or ""),
            "manufacture": str(detail.get("manufacture") or ""),
            "delivery_charge_type": str(detail.get("deliveryChargeType") or ""),
            "delivery_charge": detail.get("deliveryCharge"),
            "items": items,
        }

    def apply_fields(self, seller_product_id: str, proposed: dict[str, Any], fields: set[str]) -> dict:
        fields = set(fields) & SEO_WRITE_FIELDS
        if not fields:
            return {"ok": False, "error": "선택된 자동 반영 가능 필드가 없습니다."}
        try:
            current = copy.deepcopy(self.get_product(seller_product_id))
            before = self.current_fields(current)
            if "title" in fields and proposed.get("title"):
                title = str(proposed["title"])[:100]
                current["displayProductName"] = title
                # generalProductName is search-facing and should not contain option values.
                current["generalProductName"] = str(proposed.get("general_product_name") or title)[:100]
            if "brand" in fields and proposed.get("brand"):
                current["brand"] = str(proposed["brand"])[:100]
            if "tags" in fields:
                tags = _clean_coupang_tags(list(proposed.get("tags") or []))
                current["searchTags"] = tags
                for item in current.get("items") or []:
                    if isinstance(item, dict):
                        item["searchTags"] = tags
            if "detail" in fields and proposed.get("detail_html"):
                html = str(proposed["detail_html"])[:50000]
                for item in current.get("items") or []:
                    if isinstance(item, dict):
                        item["contents"] = [{
                            "contentsType": "HTML",
                            "contentDetails": [{"content": html, "detailType": "TEXT"}],
                        }]
            # Category/price/shipping/images/attributes are deliberately never mutated here.
            current["requested"] = True
            r = self.uploader._put(
                "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products",
                current,
            )
            if r.status_code not in (200, 201):
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:500]}", "before": before}
            return {"ok": True, "before": before, "after": self.current_fields(current), "raw": _response_json(r)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


class NaverSeoApi:
    """SEO-relevant Naver Commerce APIs (current v2 product APIs)."""

    def __init__(self, uploader=None):
        if uploader is None:
            from app.platforms.smartstore import get_smartstore_uploader
            uploader = get_smartstore_uploader()
        self.uploader = uploader

    def _get(self, path: str, params: Any = None, timeout: int = 20) -> httpx.Response:
        return httpx.get(
            f"{NAVER_API}{path}", headers=self.uploader._headers(), params=params,
            timeout=timeout,
        )

    def _put(self, path: str, body: dict, timeout: int = 40) -> httpx.Response:
        return httpx.put(
            f"{NAVER_API}{path}", headers=self.uploader._headers(), json=body,
            timeout=timeout,
        )

    def search_products(self, *, max_pages: int = 50, page_size: int = 500) -> list[dict]:
        results: list[dict] = []
        for page in range(1, max_pages + 1):
            r = httpx.post(
                f"{NAVER_API}/v1/products/search",
                headers=self.uploader._headers(),
                json={"page": page, "size": min(max(page_size, 1), 500), "orderType": "MOD_DATE"},
                timeout=30,
            )
            if r.status_code != 200:
                raise ValueError(f"네이버 상품 목록 조회 HTTP {r.status_code}: {r.text[:300]}")
            payload = _response_json(r)
            rows = payload.get("contents") or [] if isinstance(payload, dict) else []
            if not isinstance(rows, list) or not rows:
                break
            results.extend(rows)
            total_pages = int(payload.get("totalPages") or 0) if isinstance(payload, dict) else 0
            if payload.get("last") is True or (total_pages and page >= total_pages) or (not total_pages and len(rows) < page_size):
                break
        return results

    def get_product(self, origin_product_no: str) -> dict:
        r = self._get(f"/v2/products/origin-products/{origin_product_no}")
        if r.status_code != 200:
            raise ValueError(f"네이버 원상품 조회 HTTP {r.status_code}: {r.text[:400]}")
        payload = _response_json(r)
        return payload if isinstance(payload, dict) else {}

    def get_channel_product(self, channel_product_no: str) -> tuple[dict, str]:
        if not channel_product_no:
            return {}, "채널상품번호 없음"
        try:
            r = self._get(f"/v2/products/channel-products/{channel_product_no}")
            if r.status_code != 200:
                return {}, f"HTTP {r.status_code}: {r.text[:200]}"
            payload = _response_json(r)
            return (payload if isinstance(payload, dict) else {}), "ok"
        except Exception as exc:
            return {}, str(exc)

    def get_category(self, category_id: str) -> tuple[dict, str]:
        if not category_id:
            return {}, "카테고리 ID 없음"
        try:
            r = self._get(f"/v1/categories/{category_id}")
            if r.status_code != 200:
                return {}, f"HTTP {r.status_code}: {r.text[:200]}"
            payload = _response_json(r)
            return (payload if isinstance(payload, dict) else {}), "ok"
        except Exception as exc:
            return {}, str(exc)

    def get_category_attributes(self, category_id: str) -> tuple[list[dict], str]:
        if not category_id:
            return [], "카테고리 ID 없음"
        try:
            r = self._get("/v1/product-attributes/attributes", params={"categoryId": category_id})
            if r.status_code != 200:
                return [], f"HTTP {r.status_code}: {r.text[:200]}"
            payload = _response_json(r)
            rows = payload if isinstance(payload, list) else payload.get("attributes") or payload.get("contents") or []
            return ([x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []), "ok"
        except Exception as exc:
            return [], str(exc)

    def recommend_tags(self, keyword: str) -> tuple[list[dict], str]:
        keyword = str(keyword or "").strip()
        if not keyword:
            return [], "검색어 없음"
        # The API has changed parameter naming across generated SDK/doc revisions.
        # Try the current keyword form first and degrade cleanly rather than blocking an audit.
        for params in ({"keyword": keyword}, {"query": keyword}):
            try:
                r = self._get("/v2/tags/recommend-tags", params=params)
                if r.status_code == 200:
                    payload = _response_json(r)
                    rows = payload if isinstance(payload, list) else payload.get("tags") or payload.get("contents") or []
                    if isinstance(rows, list):
                        return [x for x in rows if isinstance(x, dict)], "ok"
                if r.status_code not in (400, 404):
                    return [], f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as exc:
                return [], str(exc)
        return [], "추천 태그 API 요청 파라미터가 계정/API 버전과 맞지 않음"

    def restricted_tags(self, tags: list[str]) -> tuple[dict[str, bool], str]:
        tags = [str(x).strip() for x in tags if str(x).strip()][:10]
        if not tags:
            return {}, "태그 없음"
        attempts: list[Any] = [
            [("tags", x) for x in tags],
            [("tag", x) for x in tags],
        ]
        for params in attempts:
            try:
                r = self._get("/v2/tags/restricted-tags", params=params)
                if r.status_code == 200:
                    payload = _response_json(r)
                    rows = payload if isinstance(payload, list) else payload.get("tags") or payload.get("contents") or []
                    result: dict[str, bool] = {}
                    if isinstance(rows, list):
                        for row in rows:
                            if not isinstance(row, dict):
                                continue
                            text = str(row.get("text") or row.get("tag") or row.get("name") or "").strip()
                            if text:
                                result[text] = bool(row.get("restricted"))
                    return result, "ok"
                if r.status_code not in (400, 404):
                    return {}, f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as exc:
                return {}, str(exc)
        return {}, "제한 태그 API 요청 파라미터가 계정/API 버전과 맞지 않음"

    def get_inspection_requests(self, page: int = 1, size: int = 100) -> tuple[list[dict], str]:
        try:
            r = self._get("/v1/product-inspections/channel-products", params={"page": page, "size": size})
            if r.status_code != 200:
                return [], f"HTTP {r.status_code}: {r.text[:200]}"
            payload = _response_json(r)
            rows = payload if isinstance(payload, list) else payload.get("contents") or payload.get("data") or []
            return ([x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []), "ok"
        except Exception as exc:
            return [], str(exc)

    def get_catalog_candidates(self, keyword: str, page: int = 1, size: int = 20) -> tuple[list[dict], str]:
        keyword = str(keyword or "").strip()
        if not keyword:
            return [], "검색어 없음"
        try:
            r = self._get("/v1/product-models", params={"searchKeyword": keyword, "page": page, "size": size})
            if r.status_code != 200:
                return [], f"HTTP {r.status_code}: {r.text[:200]}"
            payload = _response_json(r)
            rows = payload if isinstance(payload, list) else payload.get("contents") or payload.get("models") or []
            return ([x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []), "ok"
        except Exception as exc:
            return [], str(exc)

    @staticmethod
    def current_fields(payload: dict) -> dict[str, Any]:
        origin = payload.get("originProduct") if isinstance(payload.get("originProduct"), dict) else payload
        detail_attr = origin.get("detailAttribute") or {}
        shopping = detail_attr.get("naverShoppingSearchInfo") or {}
        seo = detail_attr.get("seoInfo") or {}
        raw_tags = seo.get("sellerTags") or []
        tags = []
        for item in raw_tags:
            if isinstance(item, dict):
                tags.append({"code": item.get("code"), "text": str(item.get("text") or "")})
            elif str(item).strip():
                tags.append({"text": str(item).strip()})
        attrs = origin.get("productAttributes") or []
        images = origin.get("images") or {}
        optional = images.get("optionalImages") or [] if isinstance(images, dict) else []
        representative = (images.get("representativeImage") or {}) if isinstance(images, dict) else {}
        delivery = origin.get("deliveryInfo") or {}
        return {
            "title": str(origin.get("name") or ""),
            "brand": str(shopping.get("brandName") or ""),
            "manufacturer": str(shopping.get("manufacturerName") or ""),
            "model_name": str(shopping.get("modelName") or ""),
            "catalog_product_id": shopping.get("catalogProductId") or shopping.get("productId") or "",
            "catalog_matching": shopping.get("catalogMatchingYn"),
            "category": str(origin.get("leafCategoryId") or ""),
            "tags": tags,
            "attributes": [x for x in attrs if isinstance(x, dict)],
            "image_count": (1 if representative.get("url") else 0) + len(optional),
            "representative_image": str(representative.get("url") or ""),
            "detail_present": bool(str(origin.get("detailContent") or "").strip()),
            "detail_html": str(origin.get("detailContent") or ""),
            "status": str(origin.get("statusType") or ""),
            "stock": int(origin.get("stockQuantity") or 0),
            "minor_purchasable": origin.get("minorPurchasable"),
            "origin_area": detail_attr.get("originAreaInfo") or {},
            "notice": detail_attr.get("productInfoProvidedNotice") or {},
            "delivery": delivery,
            "sale_price": origin.get("salePrice"),
            "page_title": str(seo.get("pageTitle") or ""),
            "meta_description": str(seo.get("metaDescription") or ""),
        }

    def apply_fields(self, origin_product_no: str, proposed: dict[str, Any], fields: set[str]) -> dict:
        fields = set(fields) & SEO_WRITE_FIELDS
        if not fields:
            return {"ok": False, "error": "선택된 자동 반영 가능 필드가 없습니다."}
        try:
            payload = copy.deepcopy(self.get_product(origin_product_no))
            before = self.current_fields(payload)
            origin = payload.get("originProduct") if isinstance(payload.get("originProduct"), dict) else payload
            detail_attr = origin.setdefault("detailAttribute", {})
            shopping = detail_attr.setdefault("naverShoppingSearchInfo", {})
            seo = detail_attr.setdefault("seoInfo", {})
            if "title" in fields and proposed.get("title"):
                origin["name"] = str(proposed["title"])[:100]
                if proposed.get("page_title"):
                    seo["pageTitle"] = str(proposed["page_title"])[:100]
            if "brand" in fields and proposed.get("brand"):
                shopping["brandName"] = str(proposed["brand"])[:100]
            if "tags" in fields:
                seo["sellerTags"] = _clean_naver_tags(list(proposed.get("tags") or []))
            if "detail" in fields and proposed.get("detail_html"):
                origin["detailContent"] = str(proposed["detail_html"])
                if proposed.get("meta_description"):
                    seo["metaDescription"] = str(proposed["meta_description"])[:160]
            # category/price/shipping/images/attributes are deliberately untouched.
            r = self._put(f"/v2/products/origin-products/{origin_product_no}", payload)
            if r.status_code not in (200, 201):
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:500]}", "before": before}
            return {"ok": True, "before": before, "after": self.current_fields(payload), "raw": _response_json(r)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


__all__ = [
    "CoupangSeoApi", "NaverSeoApi", "LOCKED_FIELDS", "SEO_WRITE_FIELDS",
    "_clean_coupang_tags", "_clean_naver_tags",
]
