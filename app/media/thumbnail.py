"""AI 상품 썸네일 생성 서비스.

상세페이지 이미지와 동일한 OpenAI 이미지 설정/안전정책을 재사용하되,
대표이미지 용도에 맞춰 1:1 구도와 상품 중심 프롬프트를 사용한다.
생성 직후 Cloudflare R2가 활성화되어 있으면 공개 저장소로 업로드한다.
"""
from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.media.ai_detail_page import _download_reference, _extract_b64, _moderation_blocked, _request_image, _safe_name
from app.media.r2_storage import publish_generated_file


@dataclass
class GeneratedThumbnail:
    local_path: str
    public_url: str
    prompt: str
    model: str


def build_thumbnail_prompt(product: dict[str, Any], *, style: str = "marketplace") -> str:
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

    style_rule = {
        "marketplace": "밝고 깨끗한 한국 이커머스 대표이미지 스타일, 중성 배경, 모바일 목록에서 즉시 식별 가능한 선명한 상품 중심 구도",
        "premium": "고급 브랜드 카탈로그 스타일, 절제된 소품과 자연광, 과장 없는 프리미엄 제품 사진",
        "lifestyle": "실제 생활공간에 자연스럽게 놓인 제품 사진이지만 상품이 화면의 주인공이며 배경은 단순하게 유지",
    }.get(str(style or "marketplace"), "밝고 깨끗한 한국 이커머스 대표이미지 스타일")

    return (
        "한국 온라인 쇼핑몰용 1:1 정사각형 상품 썸네일을 새로 촬영한 것처럼 생성한다. "
        + ", ".join(facts)
        + ". "
        + style_rule
        + ". 제품은 화면의 약 70~85%를 차지하고 형태, 색상, 비율, 재질, 버튼/구조는 reference 이미지와 일치시킨다. "
          "REFERENCE IMAGE RULE: reference는 제품 자체 확인용이며 원본 배경, 카메라 각도, 텍스트, 워터마크, 그래픽, 장식 요소를 복제하지 않는다. "
          "상품명, 가격, 할인율, 배지, 긴 문구, 가짜 브랜드 로고, 가짜 인증, 임의 스펙은 이미지 안에 넣지 않는다. "
          "제품을 자르지 말고 전체 외형이 한눈에 보이게 하며, 과한 그림자/네온/3D 렌더 느낌/공중부양을 피한다. "
          "실제 쇼핑몰 대표사진처럼 현실적인 재질과 정확한 원근감을 유지한다."
    )


def generate_thumbnail(
    product: dict[str, Any],
    *,
    reference_url: str = "",
    style: str = "marketplace",
) -> GeneratedThumbnail:
    s = get_settings()
    if not s.image_ai_enabled:
        raise RuntimeError("IMAGE_AI_ENABLED=false 입니다. 설정에서 AI 이미지 생성을 활성화하세요.")
    if (s.image_ai_provider or "openai").lower() != "openai":
        raise RuntimeError("현재 썸네일 생성기는 IMAGE_AI_PROVIDER=openai를 지원합니다.")
    if not s.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

    prompt = build_thumbnail_prompt(product, style=style)
    ref = _download_reference(reference_url)
    headers = {"Authorization": f"Bearer {s.openai_api_key.strip()}"}
    response = _request_image(
        headers=headers,
        model=s.image_ai_model,
        prompt=prompt,
        size=s.image_thumbnail_size,
        quality=s.image_thumbnail_quality,
        ref=ref,
    )
    if response.status_code not in (200, 201):
        if _moderation_blocked(response):
            raise RuntimeError(f"AI 썸네일 생성이 안전 필터에서 차단되었습니다. 원본 응답: {response.text[:350]}")
        raise RuntimeError(f"AI 썸네일 생성 실패 HTTP {response.status_code}: {response.text[:500]}")

    b64 = _extract_b64(response.json())
    if not b64:
        raise RuntimeError("AI 썸네일 생성 응답에 b64_json이 없습니다.")

    out_dir = Path(s.image_output_dir or "data/generated") / "thumbnails"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_name(str(product.get('sku') or product.get('name') or 'product'))}-thumbnail-{uuid.uuid4().hex[:8]}.png"
    path = out_dir / filename
    path.write_bytes(base64.b64decode(b64))
    public_url = publish_generated_file(path)

    return GeneratedThumbnail(
        local_path=str(path),
        public_url=public_url,
        prompt=prompt,
        model=s.image_ai_model,
    )
