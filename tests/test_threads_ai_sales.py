from app.social.threads.ai_agent import rule_classify
from app.social.threads.client import verify_webhook_signature
from app.social.threads.content_engine import suggest_comment_keyword


def test_rule_classify_shipping():
    result = rule_classify("오늘 주문하면 금요일 전에 배송돼요?")
    assert result["intent"] == "PURCHASE_INTENT" or result["intent"] == "SHIPPING"
    assert result["purchase_intent"] >= 0.7


def test_rule_classify_return_requires_human():
    result = rule_classify("불량이라 반품하고 싶어요")
    assert result["intent"] in {"RETURN", "COMPLAINT"}
    assert result["requires_human"] is True


def test_webhook_signature():
    import hashlib
    import hmac

    body = b'{"hello":"threads"}'
    secret = "secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, f"sha256={digest}", secret) is True
    assert verify_webhook_signature(body, "sha256=bad", secret) is False


def test_comment_hook_uses_known_product_feature_and_is_stable():
    product = {
        "name": "무선 차량용 청소기",
        "category": "자동차용품",
        "brand": "테스트브랜드",
        "material": "ABS",
    }
    first = suggest_comment_keyword(product)
    second = suggest_comment_keyword(product)
    assert first == second
    assert first.startswith("무선")
    assert 4 <= len(first) <= 20
