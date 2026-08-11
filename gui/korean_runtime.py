"""Streamlit 사용자 노출 문자열을 한글 표시로 통일하는 런타임 패치.

내부 DB/API 코드값, 환경변수명, URL, JSON 구조, 함수명은 변경하지 않는다.
화면에 그려지는 문자열·선택지·표 헤더·상태값만 한글로 변환한다.
"""
from __future__ import annotations

import re
from functools import wraps
from typing import Any


PHRASE_MAP: list[tuple[str, str]] = [
    ("AutoSeller AI", "오토셀러 AI"),
    ("AutoSellerAI", "오토셀러AI"),
    ("Social Commerce", "소셜커머스"),
    ("Seller OS", "판매 운영 시스템"),
    ("Growth Automation", "성장 자동화"),
    ("Profit Intelligence", "수익 인텔리전스"),
    ("AI Sales Inbox", "AI 답글함"),
    ("HOT Leads", "구매 가능 고객"),
    ("Hot Leads", "구매 가능 고객"),
    ("Tracking URL", "추적 링크"),
    ("Tracking Link", "추적 링크"),
    ("Tracking Click", "추적 클릭"),
    ("Tracking", "추적"),
    ("Content Score", "콘텐츠 점수"),
    ("AI Score", "AI 점수"),
    ("Opportunity Score", "기회 점수"),
    ("Market Score", "시장 점수"),
    ("Quality Score", "품질 점수"),
    ("Score", "점수"),
    ("Campaign Key", "캠페인 식별값"),
    ("Campaign", "캠페인"),
    ("Attribution", "구매 귀속"),
    ("Confidence", "신뢰도"),
    ("Auto Apply", "자동 적용"),
    ("Dashboard", "대시보드"),
    ("Pipeline", "파이프라인"),
    ("Analytics", "분석"),
    ("Performance", "성과"),
    ("Ranking", "순위"),
    ("Settings", "설정"),
    ("Setting", "설정"),
    ("Products", "상품"),
    ("Product", "상품"),
    ("Orders", "주문"),
    ("Order", "주문"),
    ("Inventory", "재고"),
    ("Settlement", "정산"),
    ("Revenue", "매출"),
    ("Net Profit", "순이익"),
    ("Gross Profit", "매출총이익"),
    ("Profit", "이익"),
    ("Margin Rate", "이익률"),
    ("Margin", "마진"),
    ("Platform Fee", "플랫폼 수수료"),
    ("Supply Cost", "공급 원가"),
    ("Shipping Cost", "배송비"),
    ("Return Cost", "반품 비용"),
    ("Ad Cost", "광고비"),
    ("Conversion Rate", "구매 전환율"),
    ("Conversion", "전환"),
    ("Return Rate", "반품률"),
    ("Click", "클릭"),
    ("Clicks", "클릭"),
    ("Scheduler", "스케줄러"),
    ("Schedule", "일정"),
    ("Notification", "알림"),
    ("Notifications", "알림"),
    ("Health Check", "상태 점검"),
    ("Health", "상태"),
    ("Circuit Breaker", "장애 차단기"),
    ("Rate Limiter", "호출 제한기"),
    ("Rate Limit", "호출 제한"),
    ("Service", "서비스"),
    ("Connection", "연결"),
    ("Connected", "연결됨"),
    ("Disconnected", "연결 안 됨"),
    ("Status", "상태"),
    ("Source", "출처"),
    ("Platform", "판매처"),
    ("Category", "카테고리"),
    ("Brand", "브랜드"),
    ("Keyword", "키워드"),
    ("Keywords", "키워드"),
    ("Title", "상품명"),
    ("Description", "설명"),
    ("Search Volume", "검색량"),
    ("Competition", "경쟁도"),
    ("Review", "검토"),
    ("Reviews", "리뷰"),
    ("Approve", "승인"),
    ("Reject", "반려"),
    ("Apply", "반영"),
    ("Run Now", "지금 실행"),
    ("Run", "실행"),
    ("Refresh", "새로고침"),
    ("Reload", "다시 불러오기"),
    ("Save", "저장"),
    ("Delete", "삭제"),
    ("Edit", "수정"),
    ("Add", "추가"),
    ("Create", "생성"),
    ("Upload", "업로드"),
    ("Download", "다운로드"),
    ("Export", "내보내기"),
    ("Import", "가져오기"),
    ("Search", "검색"),
    ("Filter", "필터"),
    ("All", "전체"),
    ("None", "없음"),
    ("Pending", "대기"),
    ("Ready", "준비됨"),
    ("Draft", "초안"),
    ("Listed", "판매 중"),
    ("Success", "성공"),
    ("Failed", "실패"),
    ("Error", "오류"),
    ("Active", "활성"),
    ("Inactive", "비활성"),
    ("Enabled", "사용"),
    ("Disabled", "사용 안 함"),
    ("Published", "게시 완료"),
    ("Publishing", "게시 중"),
    ("Scheduled", "예약 대기"),
    ("Completed", "완료"),
    ("Cancelled", "취소"),
    ("Returned", "반품"),
    ("Shipped", "배송 중"),
    ("Ordered", "주문 접수"),
    ("Actual", "실제"),
    ("Estimated", "추정"),
    ("Mixed", "혼합"),
    ("Deterministic", "확정"),
    ("Probabilistic", "확률"),
    ("Unattributed", "미귀속"),
    ("Text", "텍스트"),
    ("Image", "이미지"),
    ("Video", "영상"),
    ("Carousel", "슬라이드형"),
    ("Problem Solution", "문제 해결형"),
    ("Experience", "경험·공감형"),
    ("Question", "질문형"),
    ("Comparison", "비교형"),
    ("Listicle", "목록형"),
    ("Purchase Intent", "구매 의도"),
    ("Shipping", "배송"),
    ("Stock", "재고"),
    ("Price", "가격"),
    ("Compatibility", "호환성"),
    ("Product Info", "상품 정보"),
    ("Complaint", "불만·민원"),
    ("Return", "반품·환불"),
    ("Unknown", "미분류"),
    ("Human Review", "사람 검토"),
    ("Sales", "판매"),
    ("Marketplace", "판매채널"),
    ("SmartStore", "스마트스토어"),
    ("Naver", "네이버"),
    ("Coupang", "쿠팡"),
    ("Threads", "스레드"),
    ("Meta", "메타"),
    ("OAuth", "계정 인증"),
    ("Access Token", "접근 토큰"),
    ("Token", "토큰"),
    ("API Settings", "연동 설정"),
    ("API 설정", "연동 설정"),
    ("API", "연동"),
    ("SEO 최적화", "검색 최적화"),
    ("SEO", "검색 최적화"),
    ("FAQ", "자주 묻는 질문"),
    ("CTA", "행동 유도"),
    ("URL", "링크"),
    ("ID", "식별값"),
    ("KST", "한국시간"),
    ("UTC", "세계표준시"),
]

EXACT_MAP = {
    "TEXT": "텍스트",
    "IMAGE": "이미지",
    "VIDEO": "영상",
    "CAROUSEL": "슬라이드형",
    "DRAFT": "초안",
    "REVIEW_PENDING": "검수 대기",
    "APPROVED": "승인됨",
    "REJECTED": "반려됨",
    "APPLIED": "반영 완료",
    "APPLY_FAILED": "반영 실패",
    "PURCHASE_INTENT": "구매 의도",
    "SHIPPING": "배송 문의",
    "STOCK": "재고 문의",
    "PRICE": "가격 문의",
    "COMPATIBILITY": "호환성 문의",
    "PRODUCT_INFO": "상품 정보",
    "COMPLAINT": "불만·민원",
    "RETURN": "반품·환불",
    "UNKNOWN": "미분류",
    "smartstore": "네이버 스마트스토어",
    "coupang": "쿠팡",
    "threads": "스레드",
    "draft": "초안",
    "ready": "준비됨",
    "listed": "판매 중",
    "success": "성공",
    "failed": "실패",
    "pending": "대기",
    "scheduled": "예약 대기",
    "publishing": "게시 중",
    "published": "게시 완료",
    "human_review": "사람 검토 필요",
    "sent": "발송 완료",
    "cancelled": "취소",
    "ordered": "주문 접수",
    "shipped": "배송 중",
    "completed": "완료",
    "returned": "반품",
    "actual": "실제 정산",
    "mixed": "실제·추정 혼합",
    "estimated": "추정 정산",
    "deterministic": "확정 귀속",
    "probabilistic": "확률 귀속",
    "unattributed": "미귀속",
    "problem_solution": "문제 해결형",
    "experience": "경험·공감형",
    "question": "질문형",
    "comparison": "비교형",
    "listicle": "목록형",
    "ai_profit_feedback": "수익 학습 AI",
    "rule_profit_feedback": "수익 학습 규칙",
    "ai": "AI 생성",
    "rule": "규칙 생성",
    "human": "사람 작성",
}

# 코드 블록, URL, 환경변수·식별자처럼 번역하면 기능 설명이 오히려 깨지는 값.
PROTECTED_PATTERNS = (
    re.compile(r"https?://\S+"),
    re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b"),
)


def translate_text(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    if value in EXACT_MAP:
        return EXACT_MAP[value]

    # 마크다운의 인라인/블록 코드 내부는 그대로 보존한다.
    code_parts: list[str] = []
    def _hold_code(match: re.Match[str]) -> str:
        code_parts.append(match.group(0))
        return f"@@CODE{len(code_parts)-1}@@"

    text = re.sub(r"```.*?```|`[^`]+`", _hold_code, value, flags=re.DOTALL)
    for source, target in PHRASE_MAP:
        # 영단어 경계를 사용해 CSS 클래스·파이썬 식별자 내부 치환을 피한다.
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(source)}(?![A-Za-z0-9_])"
        text = re.sub(pattern, target, text, flags=re.IGNORECASE)

    for idx, code in enumerate(code_parts):
        text = text.replace(f"@@CODE{idx}@@", code)
    return text


def translate_data(value: Any) -> Any:
    if isinstance(value, str):
        return translate_text(value)
    if isinstance(value, dict):
        return {translate_text(k) if isinstance(k, str) else k: translate_data(v) for k, v in value.items()}
    if isinstance(value, list):
        return [translate_data(v) for v in value]
    if isinstance(value, tuple):
        return tuple(translate_data(v) for v in value)
    return value


def _translate_dataframe(data: Any) -> Any:
    try:
        import pandas as pd
        if isinstance(data, pd.DataFrame):
            out = data.copy()
            out.columns = [translate_text(str(c)) for c in out.columns]
            for col in out.select_dtypes(include=["object", "string"]).columns:
                out[col] = out[col].map(lambda x: translate_text(x) if isinstance(x, str) else x)
            return out
        if isinstance(data, pd.Series):
            out = data.copy()
            out.index = [translate_text(str(x)) for x in out.index]
            return out.map(lambda x: translate_text(x) if isinstance(x, str) else x)
    except Exception:
        pass
    return translate_data(data)


def _wrap_text_method(original):
    @wraps(original)
    def wrapped(self, body, *args, **kwargs):
        return original(self, translate_text(body), *args, **kwargs)
    return wrapped


def _wrap_label_method(original):
    @wraps(original)
    def wrapped(self, label, *args, **kwargs):
        return original(self, translate_text(label), *args, **kwargs)
    return wrapped


def _wrap_metric(original):
    @wraps(original)
    def wrapped(self, label, value, delta=None, *args, **kwargs):
        return original(self, translate_text(label), translate_text(value), translate_text(delta), *args, **kwargs)
    return wrapped


def _wrap_tabs(original):
    @wraps(original)
    def wrapped(self, tabs, *args, **kwargs):
        return original(self, [translate_text(x) for x in tabs], *args, **kwargs)
    return wrapped


def _wrap_select(original):
    @wraps(original)
    def wrapped(self, label, options, *args, **kwargs):
        original_format = kwargs.get("format_func")
        if original_format is None:
            kwargs["format_func"] = lambda x: translate_text(str(x))
        else:
            kwargs["format_func"] = lambda x: translate_text(original_format(x))
        return original(self, translate_text(label), options, *args, **kwargs)
    return wrapped


def _wrap_dataframe(original):
    @wraps(original)
    def wrapped(self, data=None, *args, **kwargs):
        return original(self, _translate_dataframe(data), *args, **kwargs)
    return wrapped


def _wrap_page_link(original):
    @wraps(original)
    def wrapped(self, page, *args, **kwargs):
        if "label" in kwargs and kwargs["label"] is not None:
            kwargs["label"] = translate_text(kwargs["label"])
        return original(self, page, *args, **kwargs)
    return wrapped


def apply_korean_patch() -> None:
    """Streamlit 표시 계층을 한 번만 패치한다."""
    try:
        import streamlit as st
        from streamlit.delta_generator import DeltaGenerator
    except Exception:
        return

    if getattr(st, "_autoseller_korean_patch", False):
        return

    text_methods = ["markdown", "caption", "title", "header", "subheader", "info", "warning", "success", "error", "toast", "write"]
    label_methods = ["button", "link_button", "checkbox", "toggle", "text_input", "text_area", "number_input", "slider", "date_input", "time_input", "file_uploader", "download_button", "expander", "status"]
    select_methods = ["selectbox", "multiselect", "radio", "select_slider"]

    for name in text_methods:
        if hasattr(DeltaGenerator, name):
            setattr(DeltaGenerator, name, _wrap_text_method(getattr(DeltaGenerator, name)))
    for name in label_methods:
        if hasattr(DeltaGenerator, name):
            setattr(DeltaGenerator, name, _wrap_label_method(getattr(DeltaGenerator, name)))
    for name in select_methods:
        if hasattr(DeltaGenerator, name):
            setattr(DeltaGenerator, name, _wrap_select(getattr(DeltaGenerator, name)))
    if hasattr(DeltaGenerator, "metric"):
        DeltaGenerator.metric = _wrap_metric(DeltaGenerator.metric)
    if hasattr(DeltaGenerator, "tabs"):
        DeltaGenerator.tabs = _wrap_tabs(DeltaGenerator.tabs)
    if hasattr(DeltaGenerator, "dataframe"):
        DeltaGenerator.dataframe = _wrap_dataframe(DeltaGenerator.dataframe)
    if hasattr(DeltaGenerator, "data_editor"):
        DeltaGenerator.data_editor = _wrap_dataframe(DeltaGenerator.data_editor)
    if hasattr(DeltaGenerator, "table"):
        DeltaGenerator.table = _wrap_dataframe(DeltaGenerator.table)
    if hasattr(DeltaGenerator, "page_link"):
        DeltaGenerator.page_link = _wrap_page_link(DeltaGenerator.page_link)

    # spinner는 DeltaGenerator 메서드가 아닌 모듈 함수이므로 별도로 처리한다.
    if hasattr(st, "spinner"):
        original_spinner = st.spinner
        @wraps(original_spinner)
        def spinner(text="In progress...", *args, **kwargs):
            return original_spinner(translate_text(text), *args, **kwargs)
        st.spinner = spinner

    st._autoseller_korean_patch = True
