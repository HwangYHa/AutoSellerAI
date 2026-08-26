from app.config import Settings
from app.media.thumbnail import build_thumbnail_prompt


def test_text_model_is_never_sent_to_image_api():
    settings = Settings(_env_file=None, image_ai_model="gpt-5.6-luna")
    assert settings.image_ai_model == "gpt-image-2"


def test_supported_image_model_is_preserved():
    settings = Settings(_env_file=None, image_ai_model="gpt-image-1-mini")
    assert settings.image_ai_model == "gpt-image-1-mini"


def test_thumbnail_prompt_is_square_product_first_and_fact_guarded():
    prompt = build_thumbnail_prompt(
        {
            "name": "테스트 상품",
            "category": "생활용품",
            "brand": "브랜드A",
            "origin": "대한민국",
        }
    )
    assert "1:1 정사각형" in prompt
    assert "제품은 화면의 약 70~85%" in prompt
    assert "가짜 인증" in prompt
    assert "테스트 상품" in prompt
