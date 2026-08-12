"""선택형 AI 상세페이지 이미지 생성.

원칙:
- 공급처 원본 이미지를 먼저 사용한다.
- AI 생성은 사용자가 명시적으로 요청했을 때만 실행한다.
- 가능한 경우 대표 상품 이미지를 reference image로 사용해 제품 외형 왜곡을 줄인다.
- 생성 파일은 로컬 IMAGE_OUTPUT_DIR에 저장한다.
- IMAGE_PUBLIC_BASE_URL이 설정되어 있으면 동일 파일명의 공개 URL도 반환한다.
"""
from __future__ import annotations

import base64
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import get_settings


@dataclass
class GeneratedDetailImage:
    local_path: str
    public_url: str
    prompt: str
    role: str


def _safe_name(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", text or "product").strip("-")
    return value[:50] or "product"


def build_detail_prompts(product: dict[str, Any], count: int = 3) -> list[tuple[str, str]]:
    """상세페이지에 필요한 세로형 이미지 섹션 프롬프트를 만든다."""
    name = str(product.get("name") or "상품")
    category = str(product.get("category") or "")
    brand = str(product.get("brand") or "")
    origin = str(product.get("origin") or "")
    material = str(product.get("material") or "")
    facts = [f"상품명: {name}"]
    if category:
        facts.append(f"카테고리: {category}")
    if brand:
        facts.append(f"브랜드: {brand}")
    if origin:
        facts.append(f"원산지: {origin}")
    if material:
        facts.append(f"소재: {material}")
    fact_text = ", ".join(facts)

    common = (
        "한국 온라인 쇼핑몰용 세로형 상세페이지 이미지. "
        "첨부된 reference 상품의 실제 외형, 색상, 로고, 구성품을 최대한 그대로 유지하고 "
        "보이지 않는 기능·인증·성능 수치·구성품을 임의로 추가하지 말 것. "
        f"확인된 상품 정보: {fact_text}. "
        "깔끔한 상업용 스튜디오 조명, 모바일에서 읽기 쉬운 여백과 정보 계층, 과장 광고 금지. "
        "이미지 내부의 긴 한국어 문장은 생성하지 말고 제품 중심 비주얼과 간단한 공간 구성 위주."
    )
    templates = [
        ("hero", common + " 첫 화면용 히어로 섹션. 제품을 크게 보여주고 사용 맥락이 직관적으로 보이는 프리미엄 구성."),
        ("features", common + " 핵심 특징 설명 섹션. 실제 제품에서 시각적으로 확인 가능한 특징 2~3개를 확대 컷과 여백으로 구성."),
        ("usage", common + " 실제 사용 장면 섹션. 제품 카테고리에 맞는 현실적인 사용 환경에서 제품 사용 모습을 자연스럽게 표현."),
        ("detail", common + " 소재·마감·디테일을 보여주는 클로즈업 섹션. 제품 외형을 바꾸지 말 것."),
        ("closing", common + " 상세페이지 마지막 구매검토 섹션. 제품 전체 구성을 정돈된 스튜디오 컷으로 다시 보여주는 마무리."),
    ]
    count = max(1, min(int(count), len(templates)))
    return templates[:count]


def _download_reference(url: str) -> tuple[bytes, str] | None:
    if not url or not str(url).startswith(("http://", "https://")):
        return None
    try:
        r = httpx.get(str(url), timeout=20, follow_redirects=True)
        if r.status_code != 200 or not r.content:
            return None
        content_type = (r.headers.get("content-type") or "image/jpeg").split(";", 1)[0]
        if not content_type.startswith("image/"):
            return None
        ext = {
            "image/png": ".png", "image/webp": ".webp", "image/jpeg": ".jpg",
        }.get(content_type, ".jpg")
        return r.content, ext
    except Exception:
        return None


def _extract_b64(payload: dict[str, Any]) -> str:
    data = payload.get("data") or []
    if isinstance(data, list) and data:
        item = data[0] or {}
        return str(item.get("b64_json") or "")
    return ""


def generate_detail_images(
    product: dict[str, Any],
    *,
    count: int | None = None,
    reference_url: str = "",
) -> list[GeneratedDetailImage]:
    """OpenAI GPT Image로 상세페이지용 세로 이미지를 생성한다.

    reference_url이 있으면 `/v1/images/edits`를 사용해 제품 외형 보존을 우선한다.
    reference가 없으면 `/v1/images/generations`를 사용하지만 제품 정확성 경고 대상이다.
    """
    s = get_settings()
    if not s.image_ai_enabled:
        raise RuntimeError("IMAGE_AI_ENABLED=false 입니다. 설정에서 AI 이미지 생성을 활성화하세요.")
    if (s.image_ai_provider or "openai").lower() != "openai":
        raise RuntimeError("현재 상세페이지 이미지 생성기는 IMAGE_AI_PROVIDER=openai를 지원합니다.")
    if not s.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

    count = count or s.image_ai_detail_count
    prompts = build_detail_prompts(product, count=count)
    ref = _download_reference(reference_url)
    out_dir = Path(s.image_output_dir or "data/generated")
    out_dir.mkdir(parents=True, exist_ok=True)

    headers = {"Authorization": f"Bearer {s.openai_api_key.strip()}"}
    generated: list[GeneratedDetailImage] = []

    for role, prompt in prompts:
        if ref:
            image_bytes, ext = ref
            files = {"image": (f"reference{ext}", image_bytes, "image/jpeg")}
            data = {
                "model": s.image_ai_model,
                "prompt": prompt,
                "size": s.image_ai_size,
                "quality": s.image_ai_quality,
                "output_format": "png",
            }
            response = httpx.post(
                "https://api.openai.com/v1/images/edits",
                headers=headers,
                data=data,
                files=files,
                timeout=180,
            )
        else:
            response = httpx.post(
                "https://api.openai.com/v1/images/generations",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "model": s.image_ai_model,
                    "prompt": prompt,
                    "size": s.image_ai_size,
                    "quality": s.image_ai_quality,
                    "output_format": "png",
                },
                timeout=180,
            )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"AI 이미지 생성 실패 HTTP {response.status_code}: {response.text[:500]}")
        payload = response.json()
        b64 = _extract_b64(payload)
        if not b64:
            raise RuntimeError("AI 이미지 생성 응답에 b64_json이 없습니다.")
        binary = base64.b64decode(b64)
        filename = f"{_safe_name(str(product.get('sku') or product.get('name') or 'product'))}-{role}-{uuid.uuid4().hex[:8]}.png"
        path = out_dir / filename
        path.write_bytes(binary)
        public_url = ""
        if s.image_public_base_url:
            public_url = urljoin(s.image_public_base_url.rstrip("/") + "/", filename)
        generated.append(GeneratedDetailImage(str(path), public_url, prompt, role))

    return generated


def build_detail_html(product: dict[str, Any], image_urls: list[str]) -> str:
    """공개 URL이 준비된 AI/원본 상세 이미지를 세로 상세 HTML로 조립한다."""
    name = str(product.get("name") or "상품")
    imgs = [u for u in image_urls if str(u).startswith(("http://", "https://"))]
    body = "".join(
        f'<img src="{u}" alt="{name}" style="display:block;width:100%;max-width:860px;margin:0 auto;border:0;" />'
        for u in imgs
    )
    return f'<div style="margin:0 auto;max-width:860px;background:#fff;">{body}</div>' if body else ""
