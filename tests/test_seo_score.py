"""app/seo/seo_score.py 순수 로직 테스트 (DB·Claude 호출 없는 부분만)."""
from app.seo.seo_score import _description_score, _keyword_score, _title_score


def test_title_score_ideal_length_gets_full_marks():
    assert _title_score("가나다라마바사아자차카타파하가나다라마바사", "카테고리") == 100.0


def test_title_score_too_short_is_penalized():
    assert _title_score("짧은명", "카테고리") < 100.0


def test_title_score_too_long_is_penalized():
    long_name = "가" * 80
    assert _title_score(long_name, "카테고리") < 100.0


def test_title_score_banned_word_penalized():
    with_banned = "최저가 저소음 미니 선풍기 사무실용 탁상 USB 무소음"
    without_banned = "저소음 미니 선풍기 사무실용 탁상 USB 무소음 캠핑용"
    assert _title_score(with_banned, "선풍기") < _title_score(without_banned, "선풍기")


def test_title_score_category_bonus():
    with_cat = "선풍기 저소음 미니 탁상 USB 무소음 사무실용 캠핑"
    without_cat = "저소음 미니 탁상 USB 무소음 사무실용 캠핑 휴대용품"
    assert _title_score(with_cat, "선풍기") >= _title_score(without_cat, "선풍기")


def test_title_score_empty_name_is_zero():
    assert _title_score("", "카테고리") == 0.0


def test_keyword_score_scales_with_count():
    assert _keyword_score([], 30) == 0.0
    assert _keyword_score(["a"] * 15, 30) == 50.0
    assert _keyword_score(["a"] * 30, 30) == 100.0
    assert _keyword_score(["a"] * 60, 30) == 100.0  # 100점 상한


def test_description_score_empty_is_zero():
    assert _description_score("") == 0.0


def test_description_score_rewards_length_and_structure():
    short_html = "<div>짧은 설명</div>"
    long_structured_html = "<div><h3>특징</h3><li>" + "가나다 " * 200 + "</li></div>"
    assert _description_score(long_structured_html) > _description_score(short_html)
