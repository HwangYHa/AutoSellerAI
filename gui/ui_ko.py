"""사용자 화면용 한글 표시 도우미.

DB/API 내부 값은 기존 영문 코드를 유지하고, 화면에 표시할 때만 한글로 변환한다.
외부 API와의 호환성을 깨지 않으면서 사용자 UI를 한글화하기 위한 모듈이다.
"""
from __future__ import annotations

ANGLE_LABELS = {
    "problem_solution": "문제 해결형",
    "experience": "경험·공감형",
    "question": "질문형",
    "comparison": "비교형",
    "listicle": "목록형",
}

PLATFORM_LABELS = {
    "smartstore": "네이버 스마트스토어",
    "coupang": "쿠팡",
    "threads": "스레드",
}

MEDIA_LABELS = {
    "TEXT": "텍스트",
    "IMAGE": "이미지",
    "VIDEO": "영상",
    "CAROUSEL": "슬라이드형",
}

STATUS_LABELS = {
    "draft": "초안",
    "approved": "승인",
    "scheduled": "예약 대기",
    "publishing": "게시 중",
    "published": "게시 완료",
    "pending": "대기",
    "human_review": "사람 검토 필요",
    "sent": "발송 완료",
    "failed": "실패",
    "cancelled": "취소",
    "new": "신규",
    "fulfilling": "처리 중",
    "shipped": "배송 중",
    "completed": "완료",
    "returned": "반품",
    "active": "정상",
    "expired": "만료",
    "error": "오류",
}

INTENT_LABELS = {
    "PURCHASE_INTENT": "구매 의도",
    "SHIPPING": "배송 문의",
    "STOCK": "재고 문의",
    "PRICE": "가격 문의",
    "COMPATIBILITY": "호환성 문의",
    "PRODUCT_INFO": "상품 정보",
    "COMPLAINT": "불만·민원",
    "RETURN": "반품·환불",
    "UNKNOWN": "미분류",
}

ATTRIBUTION_LABELS = {
    "deterministic": "확정 귀속",
    "probabilistic": "확률 귀속",
    "unattributed": "미귀속",
}

FINANCE_QUALITY_LABELS = {
    "actual": "실제 정산",
    "mixed": "실제·추정 혼합",
    "estimated": "추정 정산",
}

AI_SOURCE_LABELS = {
    "ai": "AI 생성",
    "ai_profit_feedback": "수익 학습 AI",
    "rule": "규칙 생성",
    "rule_profit_feedback": "수익 학습 규칙",
    "human": "사람 작성",
}


def angle_label(value: str | None) -> str:
    return ANGLE_LABELS.get(value or "", value or "-")


def platform_label(value: str | None) -> str:
    return PLATFORM_LABELS.get((value or "").lower(), value or "-")


def media_label(value: str | None) -> str:
    return MEDIA_LABELS.get((value or "").upper(), value or "-")


def status_label(value: str | None) -> str:
    return STATUS_LABELS.get((value or "").lower(), value or "-")


def intent_label(value: str | None) -> str:
    return INTENT_LABELS.get((value or "").upper(), value or "-")


def attribution_label(value: str | None) -> str:
    return ATTRIBUTION_LABELS.get((value or "").lower(), value or "-")


def finance_quality_label(value: str | None) -> str:
    return FINANCE_QUALITY_LABELS.get((value or "").lower(), value or "-")


def ai_source_label(value: str | None) -> str:
    return AI_SOURCE_LABELS.get((value or "").lower(), value or "-")
