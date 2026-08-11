from gui.korean_runtime import translate_data, translate_text


def test_common_user_terms_are_koreanized():
    text = translate_text("Dashboard · Tracking URL · Content Score · Profit Intelligence")
    assert "대시보드" in text
    assert "추적 링크" in text
    assert "콘텐츠 점수" in text
    assert "수익 인텔리전스" in text


def test_internal_status_values_are_only_translated_for_display():
    data = translate_data({"Status": "scheduled", "Platform": "smartstore", "Score": 91})
    assert data["상태"] == "예약 대기"
    assert data["판매처"] == "네이버 스마트스토어"
    assert data["점수"] == 91


def test_urls_and_environment_identifiers_are_preserved():
    raw = "Threads URL: https://graph.threads.net/v1 THREADS_APP_ID"
    translated = translate_text(raw)
    assert "https://graph.threads.net/v1" in translated
    assert "THREADS_APP_ID" in translated
    assert "스레드" in translated


def test_markdown_code_is_preserved():
    raw = "실행: `docker compose up --build` / Dashboard"
    translated = translate_text(raw)
    assert "`docker compose up --build`" in translated
    assert "대시보드" in translated
