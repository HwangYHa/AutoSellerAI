import os

from app.social.threads.content_engine import generate_threads_content


def test_content_fallback_is_safe_and_bounded(monkeypatch):
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    # Settings may have been cached by other tests; fallback behavior is still valid if API is unavailable.
    product = {
        "id": 1,
        "name": "차량용 무선 청소기",
        "category": "자동차용품",
        "brand": "",
        "origin": "중국",
        "material": "",
        "sell_price": 29900,
    }
    rows = generate_threads_content(product, angle="problem_solution", cta_keyword="청소기", count=2)
    assert len(rows) == 2
    for row in rows:
        assert row["body"]
        assert len(row["body"]) <= 500
        assert row["cta_keyword"] == "청소기"
        assert 0 <= row["score"] <= 100


def test_content_count_is_capped():
    product = {"id": 1, "name": "테스트 상품", "category": "생활", "sell_price": 10000}
    rows = generate_threads_content(product, count=99)
    assert 1 <= len(rows) <= 5
