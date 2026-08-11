from app.social.threads.search_optimization import build_search_context, fallback_optimized_body, optimization_scores


def test_build_search_context_uses_only_product_facts():
    product = {
        "name": "무선 차량용 청소기 120W",
        "category": "자동차용품",
        "brand": "테스트브랜드",
        "origin": "한국",
        "material": "ABS",
        "sell_price": 29900,
    }
    ctx = build_search_context(product)
    assert "무선" in ctx["primary_keyword"]
    assert any("브랜드" in fact for fact in ctx["entity_facts"])
    assert any("29,900원" in fact for fact in ctx["entity_facts"])
    assert ctx["faq_question"].endswith("?")


def test_fallback_threads_ad_contains_seo_geo_aeo_structure():
    product = {
        "name": "무선 차량용 청소기",
        "category": "자동차용품",
        "brand": "테스트브랜드",
        "origin": "한국",
        "sell_price": 29900,
    }
    body, ctx = fallback_optimized_body(product, "청소기")
    scores = optimization_scores(body, ctx)

    assert ctx["primary_keyword"] in body[:180]
    assert "무선 차량용 청소기" in body
    assert "Q." in body and "A." in body
    assert "29,900원" in body
    assert len(body) <= 500
    assert scores["seo_score"] >= 80
    assert scores["geo_score"] >= 75
    assert scores["aeo_score"] >= 90
