from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings


INTENT_SCORES = {
    "PURCHASE_INTENT": 0.90,
    "SHIPPING": 0.78,
    "STOCK": 0.72,
    "PRICE": 0.62,
    "COMPATIBILITY": 0.68,
    "PRODUCT_INFO": 0.52,
    "COMPARISON": 0.48,
    "COMPLAINT": 0.15,
    "RETURN": 0.10,
    "GENERAL": 0.12,
    "SPAM": 0.0,
    "UNKNOWN": 0.10,
}


def rule_classify(text: str) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    rules = [
        ("PURCHASE_INTENT", ["주문", "살게", "구매", "사고 싶", "결제"]),
        ("SHIPPING", ["배송", "도착", "언제 와", "택배", "금요일", "내일"]),
        ("STOCK", ["재고", "품절", "남았"]),
        ("PRICE", ["가격", "얼마", "할인", "원이에"]),
        ("COMPATIBILITY", ["호환", "사용 가능", "쏘렌토", "차박", "맞나요"]),
        ("RETURN", ["반품", "환불", "교환"]),
        ("COMPLAINT", ["불량", "고장", "별로", "최악"]),
    ]
    for intent, keywords in rules:
        if any(k in normalized for k in keywords):
            return {
                "intent": intent,
                "purchase_intent": INTENT_SCORES[intent],
                "sentiment": "negative" if intent in {"RETURN", "COMPLAINT"} else "neutral",
                "requires_human": intent in {"RETURN", "COMPLAINT"},
            }
    return {"intent": "UNKNOWN", "purchase_intent": 0.10, "sentiment": "neutral", "requires_human": False}


def classify_and_draft(comment: str, product: dict[str, Any] | None = None) -> dict[str, Any]:
    base = rule_classify(comment)
    settings = get_settings()
    if not settings.claude_api_key or base["requires_human"]:
        return {**base, "reply": _fallback_reply(base["intent"], product), "source": "rule"}

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.claude_api_key)
        prompt = f"""당신은 AutoSellerAI의 Threads 상품 상담 보조 AI입니다.
추측하지 말고 제공된 상품 정보 안에서만 답하세요. 상품 정보가 부족하면 확인이 필요하다고 말하세요.
과장광고, 허위 재고/배송 확답, 의료·법률 효능 주장을 하지 마세요.
댓글 의도를 아래 중 하나로 분류하세요:
PRODUCT_INFO, PRICE, STOCK, SHIPPING, COMPATIBILITY, COMPARISON, PURCHASE_INTENT, COMPLAINT, RETURN, GENERAL, SPAM, UNKNOWN

고객 댓글: {comment}
상품 정보(JSON): {json.dumps(product or {}, ensure_ascii=False)}

JSON만 반환:
{{"intent":"...","purchase_intent":0.0,"sentiment":"positive|neutral|negative","requires_human":false,"reply":"한국어 1~3문장"}}"""
        msg = client.messages.create(
            model=settings.claude_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            intent = str(data.get("intent", base["intent"]))
            score = float(data.get("purchase_intent", INTENT_SCORES.get(intent, 0.1)))
            return {
                "intent": intent,
                "purchase_intent": max(0.0, min(score, 1.0)),
                "sentiment": str(data.get("sentiment", "neutral")),
                "requires_human": bool(data.get("requires_human", False)),
                "reply": str(data.get("reply", _fallback_reply(intent, product)))[:450],
                "source": "ai",
            }
    except Exception:
        pass

    return {**base, "reply": _fallback_reply(base["intent"], product), "source": "rule"}


def _fallback_reply(intent: str, product: dict[str, Any] | None) -> str:
    name = (product or {}).get("name", "해당 상품")
    if intent == "PRICE" and product and product.get("sell_price") is not None:
        return f"{name}의 현재 등록 판매가는 {int(product['sell_price']):,}원입니다. 실제 결제가는 판매처에서 최종 확인해 주세요."
    if intent == "STOCK":
        return f"{name} 재고는 공급처와 판매처 정보 확인 후 안내드리는 것이 정확합니다."
    if intent == "SHIPPING":
        return "배송일은 주문 시점과 공급처 출고 상황에 따라 달라질 수 있어 판매처의 예상 도착일을 확인해 주세요."
    if intent in {"COMPLAINT", "RETURN"}:
        return "불편 사항은 주문 정보 확인이 필요해 자동 답변보다 담당자가 확인하는 편이 안전합니다."
    return f"{name} 관련 문의로 확인했습니다. 정확한 사양은 상품 정보 기준으로 안내드릴게요."
