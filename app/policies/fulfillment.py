"""상품별 물류/정책 값 해석기.

우선순위
1) 공급처/상품 원본의 사실정보
2) 내부 Product에 이미 저장된 사실정보
3) 판매채널 계정 기본값(API 조회값이 있으면 그 값을 사용하도록 uploader가 적용)
4) .env fallback

중요:
- A/S 연락처, 판매자 연락처, 출고지/반품지는 '판매자 계정 정책'이다.
- 원산지, 공급처 배송비, 재고, 옵션은 '상품 사실정보'다.
- 실제 발송 택배사/송장은 상품 등록 시 고정하지 않고 주문 후 공급처 응답이 최우선이다.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from app.config import get_settings


@dataclass
class FulfillmentPolicy:
    origin: str = ""
    shipping_fee: int = 0
    return_fee: int = 0
    stock: int | None = None
    support_phone: str = ""
    delivery_company_code: str = ""
    source: str = "fallback"
    provenance: dict[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provenance"] = self.provenance or {}
        return data


def _positive_or_zero(value: Any, default: int = 0) -> int:
    try:
        n = int(float(value))
        return n if n >= 0 else default
    except (TypeError, ValueError):
        return default


def _raw_lookup(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def resolve_policy_for_product(product: Any, platform: str = "") -> FulfillmentPolicy:
    """DB Product 또는 Product 유사 객체의 최신 물류정책을 계산한다.

    공급처 API가 사용 가능하면 매 업로드 직전에 상품을 재조회하여 최신 원산지,
    배송비, 재고를 사용한다. 공급처 API가 실패해도 업로드 전체를 중단하지 않고
    DB 값과 판매자 fallback으로 내려간다.
    """
    s = get_settings()
    provenance: dict[str, str] = {}

    db_origin = str(getattr(product, "origin", "") or "").strip()
    origin = db_origin
    if origin:
        provenance["origin"] = "product_db"

    shipping_fee: int | None = None
    return_fee: int | None = None
    stock: int | None = None

    supplier_id = str(getattr(product, "source", "") or "").strip()
    raw_id = str(getattr(product, "source_id", "") or "").strip()

    # 외부 마켓에서 역동기화된 상품은 공급처가 아니므로 supplier adapter 조회 제외.
    is_supplier_product = supplier_id and not supplier_id.endswith("_import")
    if is_supplier_product and raw_id:
        try:
            from app.suppliers.registry import get_adapter
            adapter = get_adapter(supplier_id)
            snapshot = adapter.get_product(raw_id) if adapter and adapter.is_available() else None
            if snapshot:
                snap_origin = str(getattr(snapshot, "origin", "") or "").strip()
                if snap_origin:
                    origin = snap_origin
                    provenance["origin"] = f"supplier:{supplier_id}"

                shipping_fee = _positive_or_zero(getattr(snapshot, "shipping_fee", None), -1)
                if shipping_fee >= 0:
                    provenance["shipping_fee"] = f"supplier:{supplier_id}"
                else:
                    shipping_fee = None

                snap_stock = getattr(snapshot, "stock", None)
                if snap_stock is not None:
                    try:
                        stock = max(0, int(snap_stock))
                        provenance["stock"] = f"supplier:{supplier_id}"
                    except (TypeError, ValueError):
                        stock = None

                raw = getattr(snapshot, "raw_data", {}) or {}
                raw_ret = _raw_lookup(raw, "return_fee", "returnFee", "return_shipping_fee", "returnShippingFee")
                if raw_ret is not None:
                    return_fee = _positive_or_zero(raw_ret, 0)
                    provenance["return_fee"] = f"supplier:{supplier_id}"
        except Exception:
            # 동적 정책 갱신 실패는 기존 DB/fallback으로 계속 진행한다.
            pass

    # 원산지가 비어 있으면 '중국'으로 임의 추정하지 않는다.
    if not origin:
        origin = (s.seller_default_origin or s.naver_origin_area_content or "기타해외").strip()
        provenance["origin"] = "seller_fallback"

    if shipping_fee is None:
        shipping_fee = max(0, int(s.seller_default_shipping_fee))
        provenance["shipping_fee"] = "seller_fallback"

    if return_fee is None:
        if platform == "coupang" and s.coupang_return_charge > 0:
            return_fee = int(s.coupang_return_charge)
            provenance["return_fee"] = "coupang_fallback"
        else:
            return_fee = max(0, int(s.seller_default_return_fee))
            provenance["return_fee"] = "seller_fallback"

    support_phone = (
        (s.coupang_company_contact_number if platform == "coupang" else "")
        or (s.naver_after_service_phone if platform == "smartstore" else "")
        or s.seller_support_phone
        or ""
    ).strip()
    provenance["support_phone"] = "seller_account"

    delivery_code = (
        (s.coupang_delivery_company_code if platform == "coupang" else "")
        or (s.naver_delivery_company_code if platform == "smartstore" else "")
        or s.seller_default_delivery_company_code
        or ""
    ).strip()
    provenance["delivery_company_code"] = "seller_account_fallback"

    return FulfillmentPolicy(
        origin=origin,
        shipping_fee=shipping_fee,
        return_fee=return_fee,
        stock=stock,
        support_phone=support_phone,
        delivery_company_code=delivery_code,
        source="supplier_live" if any(v.startswith("supplier:") for v in provenance.values()) else "fallback",
        provenance=provenance,
    )


def enrich_upload_payload(product_payload: dict[str, Any], platform: str) -> dict[str, Any]:
    """기존 업로드 payload의 하드코딩 물류값을 최신 정책으로 교체한다."""
    payload = dict(product_payload)
    sku = str(payload.get("sku", "") or "")

    product_obj = None
    if sku:
        try:
            from app.db import Product, get_db
            with get_db() as db:
                product_obj = db.query(Product).filter_by(sku=sku).first()
                if product_obj:
                    # 세션 종료 뒤에도 사용할 값만 복사
                    class P: pass
                    p = P()
                    for field in ("sku", "source", "source_id", "origin"):
                        setattr(p, field, getattr(product_obj, field, ""))
                    product_obj = p
        except Exception:
            product_obj = None

    if product_obj is None:
        class P: pass
        p = P()
        p.sku = sku
        p.source = str(payload.get("source", "") or "")
        p.source_id = str(payload.get("source_id", "") or "")
        p.origin = str(payload.get("origin", "") or "")
        product_obj = p

    policy = resolve_policy_for_product(product_obj, platform=platform)
    payload["origin"] = policy.origin
    payload["shipping_fee"] = policy.shipping_fee
    payload["return_fee"] = policy.return_fee
    if policy.stock is not None:
        payload["stock"] = policy.stock
    payload["support_phone"] = policy.support_phone
    payload["delivery_company_code"] = policy.delivery_company_code
    payload["_fulfillment_provenance"] = policy.provenance or {}
    return payload
