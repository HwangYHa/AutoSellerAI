"""기존 플랫폼 업로더에 동적 상품별 물류정책을 적용한다.

레거시 pipeline이 shipping_fee/return_fee를 상수로 넣더라도 실제 API 호출 직전에
공급처 최신 상품 + 판매자 계정 fallback으로 다시 계산해 덮어쓴다.
"""
from __future__ import annotations

_PATCHED = False


def apply_fulfillment_policy_patch() -> None:
    global _PATCHED
    if _PATCHED:
        return

    from app.policies.fulfillment import enrich_upload_payload

    from app.platforms.coupang import CoupangUploader
    original_cp = CoupangUploader.create_product

    def coupang_create(self, product: dict):
        payload = enrich_upload_payload(product, "coupang")
        # uploader 내부의 판매자 계정 fallback도 정책 해석 결과와 일치시킨다.
        if payload.get("support_phone"):
            self._contact = payload["support_phone"]
        if payload.get("return_fee") is not None:
            self._return_charge = int(payload["return_fee"])
        if payload.get("delivery_company_code"):
            try:
                from app.platforms.coupang import _normalize_delivery_code
                self._delivery_code = _normalize_delivery_code(payload["delivery_company_code"])
            except Exception:
                pass
        return original_cp(self, payload)

    CoupangUploader.create_product = coupang_create

    from app.platforms.smartstore import SmartStoreUploader
    original_ss = SmartStoreUploader.create_product

    def smartstore_create(self, product: dict):
        payload = enrich_upload_payload(product, "smartstore")
        if payload.get("support_phone"):
            self._after_service_phone = payload["support_phone"]
        if payload.get("delivery_company_code"):
            self._delivery_code = payload["delivery_company_code"]
        return original_ss(self, payload)

    SmartStoreUploader.create_product = smartstore_create
    _PATCHED = True
