from app.social.threads.content_engine import _fallback_variants, suggest_comment_keyword
from app.social.threads.copy_quality import copy_quality_issues, natural_product_name, sales_copy_score


def _adult_evidence():
    return {
        "verified": {
            "name": "프리티러브 프리다 성인용품 여성용품 여성자위기구 딜도 진동기 바이브레이터 자위기구 yhw084jq",
            "sku": "ONC-yhw084jq",
            "source_id": "yhw084jq",
            "category": "63815",
            "brand": "프리티러브",
            "origin": "중국",
            "material": "",
            "sell_price": 45090,
            "options": [],
            "stored_detail_text": "",
        },
        "evidence_stats": {},
    }


def test_supplier_keyword_title_is_reduced_to_human_brand_model_name():
    assert natural_product_name(_adult_evidence()["verified"]) == "프리티러브 프리다"


def test_quality_gate_rejects_ids_keyword_stuffing_and_unsupported_sales_judgment():
    evidence = _adult_evidence()
    body = (
        "프리티러브 프리다 성인용품 여성용품 여성자위기구 딜도 진동기 바이브레이터 자위기구 yhw084jq. "
        "63815 제품이고 가격대가 진입 장벽이 낮은 편이야. 정품 여부만 확인하면 괜찮은 선택지야. "
        "댓글에 '선택팁' 남겨줘."
    )
    score, issues = sales_copy_score(body, evidence, "선택팁")
    assert score < 50
    assert "numeric_category" in issues
    assert "keyword_stuffing" in issues
    assert "unsupported_or_template_judgment" in issues
    assert any(x.startswith("internal_") for x in issues)


def test_adult_product_auto_cta_is_curiosity_hook_not_raw_seo_phrase():
    product = {
        "name": "프리티러브 프리다 성인용품 여성용품 여성자위기구 딜도 진동기 바이브레이터",
        "category": "63815",
        "brand": "프리티러브",
    }
    keyword = suggest_comment_keyword(product)
    assert keyword in {"선택팁", "입문팁", "비교포인트", "관리팁", "체크포인트"}
    assert "성인용품" not in keyword
    assert "자위기구" not in keyword


def test_fallback_never_exposes_internal_catalog_fields_or_full_seo_title():
    evidence = _adult_evidence()
    product = dict(evidence["verified"])
    rows = _fallback_variants(
        product,
        "experience",
        "선택팁",
        2,
        image_url="",
        evidence=evidence,
    )
    assert len(rows) == 2
    for row in rows:
        body = row["body"]
        assert "63815" not in body
        assert "yhw084jq" not in body
        assert "여성자위기구 딜도 진동기 바이브레이터 자위기구" not in body
        assert not copy_quality_issues(body, evidence, "선택팁")
