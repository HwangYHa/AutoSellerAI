"""app/seo/title_gen.py 순수 로직 테스트 (금지어 필터)."""
from app.seo.title_gen import _contains_banned


def test_contains_banned_detects_prohibited_word():
    assert _contains_banned("초특가 무료배송 이벤트 상품")


def test_contains_banned_allows_clean_title():
    assert not _contains_banned("저소음 미니 탁상 선풍기 사무실용 캠핑")
