"""app/seo/duplicate_detector.py 순수 로직 테스트 (정규화 규칙, DB 없이)."""
from app.seo.duplicate_detector import _normalize


def test_normalize_strips_special_characters():
    assert _normalize("USB-선풍기(2026년형)!!") == "usb 선풍기 2026년형"


def test_normalize_collapses_whitespace():
    assert _normalize("저소음   미니    선풍기") == "저소음 미니 선풍기"


def test_normalize_shared_prefix_beyond_30_chars_is_treated_as_duplicate():
    # find_duplicates()는 정규화된 이름의 앞 30자만 비교한다 — 같은 기본상품에
    # 캠페인/시즌 접미사만 다르게 붙인 흔한 패턴을 재현.
    common_prefix = "가" * 30
    a = _normalize(common_prefix + " 사무실용 특가할인")
    b = _normalize(common_prefix + " 캠핑용 신상품출시")
    assert a[:30] == b[:30] == common_prefix
