from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_IMAGE_MODELS = {"gpt-image-2", "gpt-image-1.5", "gpt-image-1-mini"}


class Settings(BaseSettings):
    """AutoSellerAI 런타임 설정.

    원칙:
    - 상품 사실정보(원산지/공급처 배송비/재고/옵션)는 공급처 또는 기존 마켓 상품에서 읽는다.
    - 판매자 계정정보(A/S 연락처/출고지/반품지)는 판매채널 API 계정값을 우선한다.
    - 환경변수의 배송/반품 관련 값은 API 조회가 불가능할 때만 사용하는 fallback이다.
    - 상품 이미지/상세이미지는 공급처 API와 원본 HTML 태그를 우선 사용하고 AI 생성은 선택 기능이다.
    """

    # 애플리케이션 / 보안
    app_name: str = "AutoSellerAI"
    env: str = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    secret_key: str = ""
    access_token_expire_minutes: int = 1440
    algorithm: str = "HS256"

    # 데이터 / 작업 큐
    # local: DATABASE_URL 비우고 SQLite 사용. production: PostgreSQL DATABASE_URL 권장.
    database_url: str = ""
    db_path: str = "data/autoseller.db"
    redis_url: str = "redis://localhost:6379/0"

    # 공통 판매자 fallback — 플랫폼 API/상품 데이터가 없을 때만 사용
    seller_support_phone: str = ""
    seller_default_shipping_fee: int = 3000
    seller_default_return_fee: int = 3000
    seller_default_origin: str = ""
    seller_default_delivery_company_code: str = ""

    # 네이버 스마트스토어
    naver_client_id: str = ""
    naver_client_secret: str = ""
    naver_login_id: str = ""
    naver_login_pw: str = ""
    naver_after_service_phone: str = ""
    naver_origin_area_content: str = ""
    naver_delivery_company_code: str = ""

    # 쿠팡 Wing API
    coupang_access_key: str = ""
    coupang_secret_key: str = ""
    coupang_vendor_id: str = ""
    coupang_vendor_user_id: str = ""
    coupang_outbound_shipping_place_code: int = 0
    coupang_return_center_code: str = ""
    coupang_return_zip_code: str = ""
    coupang_return_address: str = ""
    coupang_return_address_detail: str = ""
    coupang_company_contact_number: str = ""
    coupang_return_charge: int = 0
    coupang_delivery_company_code: str = ""

    # 공급처
    domeggook_api_key: str = ""
    domeggook_user_id: str = ""
    domeggook_password: str = ""
    domemai_api_key: str = ""
    onchannel_login_id: str = ""
    onchannel_login_pw: str = ""

    # 오너클랜 판매사 API (JWT + GraphQL)
    ownerclan_username: str = ""
    ownerclan_password: str = ""
    ownerclan_environment: str = "production"

    # 자동 주문/발주/송장 연동 정책
    # 실제 공급처 결제가 발생할 수 있으므로 기본값은 OFF. 사용자가 로컬 .env에서 명시적으로 켠다.
    fulfillment_auto_purchase_enabled: bool = False
    fulfillment_auto_tracking_enabled: bool = True
    fulfillment_poll_interval_seconds: int = 60
    fulfillment_max_order_krw: int = 100000
    fulfillment_min_profit_krw: int = 500
    fulfillment_min_margin_pct: float = 0.05
    fulfillment_supplier_allowlist: str = ""
    fulfillment_max_items_per_cycle: int = 50

    # 판매 운영 자동화
    # 외부 판매중지/재개는 실제 판매에 영향을 주므로 기본 OFF. UI/환경설정에서 명시적으로 활성화한다.
    inventory_auto_visibility_enabled: bool = False
    inventory_low_stock_confirmations: int = 2
    inventory_restock_confirmations: int = 2
    inventory_restock_buffer: int = 1
    inquiry_ai_draft_enabled: bool = True
    inquiry_auto_answer_enabled: bool = False
    inquiry_ai_max_chars: int = 1200
    settlement_sync_days: int = 31
    claim_sync_hours: int = 72
    inquiry_sync_days: int = 7
    # 공급처별 결제 방식 JSON 예: {"ownerclan":"balance","onchannel":"interactive_card"}
    supplier_payment_modes_json: str = "{}"
    payment_session_expire_minutes: int = 20

    # 네이버 쇼핑 검색 + 데이터랩
    naver_search_client_id: str = ""
    naver_search_client_secret: str = ""

    # Claude AI
    claude_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_model_light: str = "claude-haiku-4-5-20251001"
    claude_model_heavy: str = "claude-sonnet-4-6"

    # OpenAI / AI 이미지 상세페이지 · 썸네일
    openai_api_key: str = ""
    image_ai_enabled: bool = False
    image_ai_auto_generate: bool = False
    image_ai_provider: str = "openai"
    image_ai_model: str = "gpt-image-2"
    image_ai_size: str = "1024x1536"
    image_ai_quality: str = "medium"
    image_ai_detail_count: int = 3
    image_thumbnail_size: str = "1024x1024"
    image_thumbnail_quality: str = "medium"
    image_source_page_fetch: bool = True
    image_output_dir: str = "data/generated"
    image_public_base_url: str = ""
    image_cdn_base_url: str = ""

    # Cloudflare R2 — S3 호환 object storage
    r2_enabled: bool = False
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_endpoint: str = ""
    r2_object_prefix: str = "generated"
    r2_region: str = "auto"
    r2_cache_control: str = "public, max-age=31536000, immutable"

    @field_validator("image_ai_model", mode="before")
    @classmethod
    def normalize_image_model(cls, value):
        """이미지 endpoint에 텍스트 GPT 모델이 전달되는 사고를 차단한다."""
        model = str(value or "").strip()
        return model if model in _IMAGE_MODELS else "gpt-image-2"

    # 텔레그램 알림
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Threads / Meta
    threads_app_id: str = ""
    threads_app_secret: str = ""
    threads_oauth_redirect_uri: str = ""
    threads_oauth_success_url: str = ""
    seller_gui_url: str = "http://localhost:8501"
    threads_token_encryption_key: str = ""
    threads_verify_token: str = ""
    threads_graph_base_url: str = "https://graph.threads.net"
    threads_user_id: str = ""
    threads_access_token: str = ""

    # 스케줄러
    scheduler_enabled: bool = True
    scheduler_timezone: str = "Asia/Seoul"

    # 가격 필터
    min_margin_pct: float = 0.15
    min_price: int = 1000
    max_price: int = 300000

    # SEO 최적화
    seo_review_mode_enabled: bool = True
    seo_min_keywords: int = 30
    seo_title_candidates: int = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


_settings_cache: Settings | None = None


def get_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


def reload_settings() -> Settings:
    """설정 캐시를 무효화하고 .env를 재로드한다."""
    global _settings_cache
    _settings_cache = None
    return get_settings()
