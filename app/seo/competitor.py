"""경쟁사 상품 URL 분석 — app/market/coupang_best.py와 동일한 스크래핑 컨벤션
(UA/Referer 헤더, httpx.Client, 실패시 graceful fallback)을 재사용한다.

쿠팡/스마트스토어 상품 상세페이지는 로그인·봇 차단 등으로 안정적으로 파싱하기
어려우므로 best-effort로 <title>/메타 설명만 추출하고, 실패 시 error를 채워
호출자가 "분석 불가" 상태를 그대로 사용자에게 보여줄 수 있게 한다.
"""
from __future__ import annotations
import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _fetch_meta(url: str) -> dict:
    try:
        with httpx.Client(headers=_HEADERS, timeout=15, follow_redirects=True) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            return {"ok": False, "error": f"HTTP {resp.status_code}"}

        soup = BeautifulSoup(resp.text, "lxml")
        title_el = soup.select_one("title")
        og_title = soup.select_one("meta[property='og:title']")
        og_desc = soup.select_one("meta[property='og:description']")
        return {
            "ok": True,
            "title": (og_title.get("content") if og_title else None) or (title_el.get_text(strip=True) if title_el else ""),
            "description": og_desc.get("content") if og_desc else "",
        }
    except Exception as exc:
        logger.warning("경쟁사 페이지 수집 실패: %s", exc)
        return {"ok": False, "error": str(exc)}


def analyze_competitor(url: str) -> dict:
    """경쟁사 상품 URL에서 제목/설명을 추출하고 Claude로 강약점을 분석한다.

    Returns:
        {"ok": bool, "title": str, "description": str,
         "keywords": [str], "strengths": [str], "weaknesses": [str], "error": str}
    """
    meta = _fetch_meta(url)
    if not meta.get("ok"):
        return {"ok": False, "title": "", "description": "", "keywords": [],
                "strengths": [], "weaknesses": [], "error": meta.get("error", "수집 실패")}

    result = {**meta, "keywords": [], "strengths": [], "weaknesses": [], "error": ""}

    s = get_settings()
    if not s.claude_api_key or not meta.get("title"):
        return result

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=s.claude_api_key)
        msg = client.messages.create(
            model=s.claude_model,
            max_tokens=800,
            messages=[{"role": "user", "content": f"""
한국 이커머스 SEO 분석가입니다. 아래 경쟁사 상품 정보를 보고 핵심 키워드,
장점, 약점을 분석하세요.

제목: {meta.get('title')}
설명: {meta.get('description', '')}

JSON으로만 응답:
{{"keywords": ["키워드1", ...], "strengths": ["장점1", ...], "weaknesses": ["약점1", ...]}}"""}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            result["keywords"] = data.get("keywords", [])
            result["strengths"] = data.get("strengths", [])
            result["weaknesses"] = data.get("weaknesses", [])
    except Exception as exc:
        logger.warning("경쟁사 분석(Claude) 실패: %s", exc)

    return result
