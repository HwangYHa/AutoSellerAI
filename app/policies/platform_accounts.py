"""판매채널 계정의 출고/반품 기본값을 API에서 조회한다.

상품 사실정보와 판매자 계정 정책을 분리하기 위한 모듈이다.
조회 실패 시 기존 .env fallback을 그대로 유지한다.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _first_dict(data: Any) -> dict:
    if isinstance(data, list):
        return next((x for x in data if isinstance(x, dict)), {})
    if isinstance(data, dict):
        for key in ("content", "contents", "items"):
            value = data.get(key)
            if isinstance(value, list) and value:
                return _first_dict(value)
        nested = data.get("data")
        if nested is not None and nested is not data:
            found = _first_dict(nested)
            if found:
                return found
        return data
    return {}


def hydrate_coupang_account_defaults(uploader) -> dict[str, str]:
    """Wing에 등록된 출고지/반품지를 읽어 uploader 기본값을 갱신한다.

    반환값은 어떤 필드를 API에서 채웠는지 나타내는 provenance다.
    실패해도 예외를 밖으로 내보내지 않아 .env fallback이 계속 동작한다.
    """
    provenance: dict[str, str] = {}

    # 출고지 목록
    try:
        path = (
            "/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound"
            "?pageSize=50&pageNum=1"
        )
        r = uploader._get(path)
        if r.status_code == 200:
            row = _first_dict(r.json())
            code = (
                row.get("outboundShippingPlaceCode")
                or row.get("placeCode")
                or row.get("shippingPlaceCode")
            )
            if code:
                uploader._outbound_code = int(code)
                provenance["outbound_shipping_place"] = "coupang_api"
    except Exception as exc:
        logger.debug("쿠팡 출고지 자동조회 실패, fallback 사용: %s", exc)

    # 반품지 목록
    try:
        vendor_id = getattr(uploader, "_vendor_id", "")
        if vendor_id:
            path = (
                f"/v2/providers/openapi/apis/api/v5/vendors/{vendor_id}/returnShippingCenters"
                "?pageNum=1&pageSize=50"
            )
            r = uploader._get(path)
            if r.status_code == 200:
                row = _first_dict(r.json())
                code = row.get("returnCenterCode")
                if code:
                    uploader._return_code = int(code)
                    provenance["return_center"] = "coupang_api"

                deliver_code = row.get("deliverCode") or row.get("deliveryCompanyCode")
                if deliver_code:
                    try:
                        from app.platforms.coupang import _normalize_delivery_code
                        uploader._delivery_code = _normalize_delivery_code(str(deliver_code))
                        provenance["delivery_company"] = "coupang_api"
                    except Exception:
                        pass

                # 반품비: API가 제공하는 대표 5kg 반품비를 우선 사용
                for key in ("returnFee05kg", "returnFee02kg", "returnFee10kg", "returnCharge"):
                    fee = row.get(key)
                    if fee not in (None, ""):
                        try:
                            uploader._return_charge = int(float(fee))
                            provenance["return_fee"] = "coupang_api"
                            break
                        except (TypeError, ValueError):
                            pass

                # API 응답 스키마 버전에 따라 주소 필드가 평면/중첩일 수 있어 둘 다 처리
                addr = row.get("returnAddress") if isinstance(row.get("returnAddress"), dict) else row
                zip_code = addr.get("returnZipCode") or addr.get("zipCode") or addr.get("postalCode")
                address = addr.get("returnAddress") or addr.get("address") or addr.get("address1")
                detail = addr.get("returnAddressDetail") or addr.get("addressDetail") or addr.get("address2")
                phone = row.get("companyContactNumber") or row.get("phoneNumber") or row.get("phoneNumber2")
                if zip_code:
                    uploader._return_zip = str(zip_code)
                if address:
                    uploader._return_addr = str(address)
                if detail:
                    uploader._return_addr_detail = str(detail)
                if phone:
                    uploader._contact = str(phone)
                if any((zip_code, address, detail, phone)):
                    provenance["return_contact"] = "coupang_api"
    except Exception as exc:
        logger.debug("쿠팡 반품지 자동조회 실패, fallback 사용: %s", exc)

    return provenance
