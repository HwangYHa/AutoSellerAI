from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # SQLite DB 경로 (로컬: data/autoseller.db, Docker 볼륨 마운트와 호환)
    db_path: str = "data/autoseller.db"

    # 네이버 스마트스토어
    naver_client_id: str = ""
    naver_client_secret: str = ""
    naver_login_id: str = ""
    naver_login_pw: str = ""
    naver_after_service_phone: str = "010-0000-0000"
    naver_origin_area_content: str = "중국"
    naver_delivery_company_code: str = "CJGLS"

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
    coupang_return_charge: int = 3000
    coupang_delivery_company_code: str = "CJGLS"

    # 공급처
    domeggook_api_key: str = ""
    domeggook_user_id: str = ""
    domeggook_password: str = ""
    domemai_api_key: str = ""        # 도매매 API 키
    onchannel_login_id: str = ""
    onchannel_login_pw: str = ""

    # 오너클랜 판매사 API (JWT + GraphQL)
    ownerclan_username: str = ""
    ownerclan_password: str = ""
    ownerclan_environment: str = "production"  # production | sandbox

    # 네이버 쇼핑 검색 + 데이터랩 (같은 클라이언트 키 사용)
    naver_search_client_id: str = ""
    naver_search_client_secret: str = ""

    # Claude AI
    claude_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_model_heavy: str = "claude-sonnet-4-6"  # 시장 분석 등 복잡한 추론

    # 텔레그램 알림
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # 스케줄러
    scheduler_enabled: bool = True
    scheduler_timezone: str = "Asia/Seoul"

    # 가격 필터
    min_margin_pct: float = 0.15
    min_price: int = 1000
    max_price: int = 300000

    # SEO 최적화
    seo_review_mode_enabled: bool = True    # 항상 사람 승인 후 반영 (끌 수 없음, 안전장치)
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
