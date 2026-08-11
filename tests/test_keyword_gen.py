"""app/seo/keyword_gen.py 순수 로직 테스트 (Claude 미호출 폴백 경로)."""
from app.seo.keyword_gen import _dedupe, _fallback_keywords


def test_dedupe_removes_case_insensitive_duplicates():
    assert _dedupe(["USB선풍기", "usb선풍기", "USB선풍기 "]) == ["USB선풍기"]


def test_dedupe_preserves_order_of_first_occurrence():
    assert _dedupe(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]


def test_dedupe_drops_empty_strings():
    assert _dedupe(["", "  ", "키워드"]) == ["키워드"]


def test_fallback_keywords_includes_category_and_tokens():
    result = _fallback_keywords("저소음 USB 탁상 선풍기", "생활가전", "브랜드없음")
    assert "생활가전" in result["keywords"]
    assert "USB" in result["keywords"]
    assert result["tags"][0] == "생활가전"


def test_fallback_keywords_has_no_duplicates():
    result = _fallback_keywords("선풍기 선풍기 미니 선풍기", "선풍기", "")
    assert len(result["keywords"]) == len(set(k.casefold() for k in result["keywords"]))
