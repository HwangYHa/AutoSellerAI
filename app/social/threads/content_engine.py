from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings


ANGLES = {
    "problem_solution": "문제 해결형",
    "experience": "경험/공감형",
    "question": "질문형",
    "comparison": "비교형",
    "listicle": "리스트형",
}


def generate_threads_content(product: dict[str, Any], angle: str = "problem_solution",
                             cta_keyword: str = "", count: int = 3) -> list[dict[str, Any]]:
    angle = angle if angle in ANGLES else "problem_solution"
    count = max(1, min(int(count), 5))
    settings = get_settings()

    if settings.claude_api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.claude_api_key)
            prompt = f"""당신은 한국 이커머스 Threads 콘텐츠 에디터입니다.
광고문구처럼 밀어붙이지 말고 정보/공감형 콘텐츠를 작성하세요.
상품 DB에 없는 성능, 인증, 배송일, 할인율, 최저가를 추측하거나 만들지 마세요.
본문은 500자 이하, 과장표현·허위후기·가짜 사용경험 금지입니다.
CTA는 자연스럽게 댓글 참여를 유도하되 스팸성 반복을 피하세요.

상품정보(JSON): {json.dumps(product, ensure_ascii=False)}
콘텐츠 각도: {ANGLES[angle]}
CTA 키워드: {cta_keyword or '상품명에서 자연스럽게 1개 생성'}
후보 수: {count}

JSON 배열만 반환하세요.
각 항목: {{"body":"...","cta_keyword":"...","score":0~100,"reason":"짧은 이유"}}
"""
            msg = client.messages.create(
                model=settings.claude_model,
                max_tokens=1800,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                rows = json.loads(match.group())
                result = []
                for row in rows[:count]:
                    body = str(row.get("body", "")).strip()[:500]
                    if not body:
                        continue
                    keyword = str(row.get("cta_keyword", cta_keyword)).strip()[:100]
                    score = float(row.get("score", 70))
                    result.append({
                        "body": body,
                        "cta_keyword": keyword,
                        "score": max(0.0, min(score, 100.0)),
                        "reason": str(row.get("reason", "AI 생성"))[:200],
                        "source": "ai",
                    })
                if result:
                    return result
        except Exception:
            pass

    return _fallback_variants(product, angle, cta_keyword, count)


def _fallback_variants(product: dict[str, Any], angle: str, cta_keyword: str, count: int) -> list[dict[str, Any]]:
    name = str(product.get("name") or "이 상품")
    category = str(product.get("category") or "생활")
    keyword = cta_keyword.strip() or _keyword_from_name(name)
    templates = {
        "problem_solution": [
            f"{category} 제품 고를 때 의외로 놓치기 쉬운 게 있습니다. 기능이 많아 보여도 실제 사용 상황에 맞는지가 더 중요하더라고요. 지금 비교 중인 제품은 ‘{name}’입니다. 궁금한 점이 있으면 ‘{keyword}’라고 댓글 남겨주세요.",
            f"비슷한 제품이 많을수록 가격만 보고 고르기 어려워집니다. 저는 먼저 사용 목적과 옵션을 확인하는 편입니다. 현재 확인 중인 제품은 {name}입니다. 정보가 필요하면 댓글에 ‘{keyword}’라고 남겨주세요.",
        ],
        "experience": [
            f"상품을 볼 때 처음엔 이름보다 ‘내가 실제로 언제 쓰게 될까’를 먼저 생각하게 됩니다. {name}도 그런 관점에서 보고 있어요. 스펙과 판매정보가 궁금하면 ‘{keyword}’라고 남겨주세요.",
            f"요즘 {category} 제품을 비교하면서 느낀 건 화려한 문구보다 기본 정보가 정확한 게 훨씬 중요하다는 점입니다. {name} 정보가 궁금하면 ‘{keyword}’라고 댓글 주세요.",
        ],
        "question": [
            f"{category} 제품 살 때 여러분은 가격, 디자인, 사용편의 중 어떤 걸 먼저 보세요? 지금 {name}을 비교 중인데, 상세 정보가 궁금하면 ‘{keyword}’라고 남겨주세요.",
            f"비슷한 상품이 여러 개면 어떤 기준으로 고르시나요? 현재 확인 중인 {name} 관련 정보를 정리하고 있습니다. 필요하면 댓글에 ‘{keyword}’라고 남겨주세요.",
        ],
        "comparison": [
            f"싼 제품 하나를 바로 고르는 것 vs 용도에 맞는지 먼저 확인하는 것. 저는 두 번째를 택합니다. 지금 비교 중인 제품은 {name}. 정보가 필요하면 ‘{keyword}’라고 남겨주세요.",
            f"상품 비교할 때 ‘가격만 낮은 제품’과 ‘필요한 조건이 맞는 제품’은 다르더라고요. {name}을 기준으로 체크 중입니다. 궁금하면 ‘{keyword}’라고 댓글 주세요.",
        ],
        "listicle": [
            f"{category} 제품 고를 때 체크할 것 3가지. 1) 실제 사용 목적 2) 옵션/규격 3) 최종 결제조건. 지금 {name}도 같은 기준으로 보고 있습니다. 정보가 필요하면 ‘{keyword}’라고 남겨주세요.",
            f"구매 전에 확인하면 좋은 것: 가격, 옵션, 사용환경, 배송조건. {name} 관련 정보도 이 기준으로 정리 중입니다. 궁금하면 ‘{keyword}’라고 댓글 주세요.",
        ],
    }
    rows = templates.get(angle, templates["problem_solution"])
    result = []
    while len(result) < count:
        body = rows[len(result) % len(rows)][:500]
        result.append({"body": body, "cta_keyword": keyword, "score": 65.0, "reason": "규칙 기반 안전 초안", "source": "rule"})
    return result


def _keyword_from_name(name: str) -> str:
    words = re.sub(r"[^0-9A-Za-z가-힣 ]", " ", name).split()
    return (words[0] if words else "정보")[:20]
