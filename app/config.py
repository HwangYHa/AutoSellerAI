from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """AutoSellerAI 런타임 설정.

    원칙:
    - 상품 사실정보(원산지/공급처 배송비/재고/옵션)는 공급처 또는 기존 마켓 상품에서 읽는다.
    - 판매자 계정정보(A/S 연락처/출고지/반품지)는 판매채널 API 계정값을 우선한다.
    - 환경변수의 배송/반품 관련 값은 API 조회가 불가능할 때만 사용하는 fallback이다.
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

    # SQLite DB 경로 (현재 Seller OS 주 데이터베이스)
    db_path: str = "data/autoseller.db"

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
    # 아래 3개는 fallback. 상품/판매자 API에서 얻은 값이 우선한다.
    naver_after_service_phone: str = ""
    naver_origin_area_content: str = ""
    naver_delivery_company_code: str = ""

    # 쿠팡 Wing API
    coupang_access_key: str = ""
    coupang_secret_key: str = ""
    coupang_vendor_id: str = ""
    coupang_vendor_user_id: str = ""
    # 출고지/반품지는 API 자동조회 우선, 아래 값은 fallback
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
    ownerclan_environment: str = "production"  # production | sandbox

    # 네이버 쇼핑 검색 + 데이터랩
    naver_search_client_id: str = ""
    naver_search_client_secret: str = ""

    # Claude AI
    claude_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_model_light: str = "claude-haiku-4-5-20251001"
    claude_model_heavy: str = "claude-sonnet-4-6"

    # OpenAI 보조 기능
    openai_api_key: str = ""

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
