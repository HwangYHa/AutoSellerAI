from app.social.threads.content_engine import suggest_comment_keyword
from app.social.threads.product_analysis import _safe_public_url, build_product_evidence


def test_product_evidence_keeps_verified_detail_options_and_images():
    product = {
        "name": "무선 미니 청소기",
        "category": "자동차용품",
        "brand": "테스트",
        "material": "ABS",
        "sell_price": 19900,
        "options": [{"name": "색상", "values": ["블랙", "화이트"]}],
        "images": ["https://example.com/main.jpg"],
        "detail_images": ["https://example.com/detail.jpg"],
        "detail_html": "<div><b>무선</b> 충전식 제품이며 차량 내부 정리에 사용하는 상품입니다.</div>",
    }
    evidence = build_product_evidence(product)
    verified = evidence["verified"]
    assert verified["name"] == "무선 미니 청소기"
    assert verified["options"]
    assert verified["images"] == ["https://example.com/main.jpg"]
    assert "충전식" in verified["stored_detail_text"]
    assert evidence["evidence_stats"]["stored_detail_chars"] > 0


def test_product_page_fetch_blocks_local_and_private_literal_addresses():
    assert _safe_public_url("http://localhost:8501/product") is False
    assert _safe_public_url("http://127.0.0.1/product") is False
    assert _safe_public_url("http://192.168.0.10/product") is False
    assert _safe_public_url("https://example.com/product") is True


def test_comment_keyword_uses_verified_product_feature():
    keyword = suggest_comment_keyword({
        "name": "무선 차량용 청소기",
        "category": "자동차용품",
        "material": "ABS",
        "options": [],
    })
    assert keyword.startswith("무선")
    assert len(keyword) <= 20
