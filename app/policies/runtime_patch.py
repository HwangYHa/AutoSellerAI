"""기존 플랫폼 업로더에 동적 상품별 물류정책을 적용한다.

레거시 pipeline이 shipping_fee/return_fee를 상수로 넣더라도 실제 API 호출 직전에
공급처 최신 상품 + 판매채널 계정 API + .env fallback 순으로 다시 계산한다.
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
        # 출고지/반품지/계약 택배사 등은 상품 데이터가 아니라 판매자 계정 정책이므로
        # Wing API에서 먼저 읽는다. 실패하면 기존 .env fallback이 유지된다.
        try:
            from app.policies.platform_accounts import hydrate_coupang_account_defaults
            account_provenance = hydrate_coupang_account_defaults(self)
        except Exception:
            account_provenance = {}

        payload = enrich_upload_payload(product, "coupang")
        provenance = payload.get("_fulfillment_provenance") or {}

        # 공급처가 상품별 반품비를 명시한 경우만 계정 기본 반품비보다 우선한다.
        ret_source = str(provenance.get("return_fee", ""))
        if ret_source.startswith("supplier:") or "return_fee" not in account_provenance:
            if payload.get("return_fee") is not None:
                self._return_charge = int(payload["return_fee"])

        # API에서 판매자 연락처/택배사를 얻지 못한 경우에만 fallback을 적용한다.
        if "return_contact" not in account_provenance and payload.get("support_phone"):
            self._contact = payload["support_phone"]
        if "delivery_company" not in account_provenance and payload.get("delivery_company_code"):
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
        # 네이버 업로더는 create_product 내부에서 출고지/반품지 API 자동조회를 이미 수행한다.
        # A/S 연락처와 기본 택배사만 환경변수 fallback으로 보완한다.
        if payload.get("support_phone"):
            self._after_service_phone = payload["support_phone"]
        if payload.get("delivery_company_code"):
            self._delivery_code = payload["delivery_company_code"]
        return original_ss(self, payload)

    SmartStoreUploader.create_product = smartstore_create
    _PATCHED = True
