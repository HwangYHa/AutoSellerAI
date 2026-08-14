"""선택형 AI 상세페이지 이미지 생성.

원칙:
- 공급처 원본 이미지를 먼저 사용한다.
- AI 생성은 사용자가 명시적으로 요청했을 때만 실행한다.
- 가능한 경우 대표 상품 이미지를 reference image로 사용해 제품 외형 왜곡을 줄인다.
- 민감/성인 전용 상품은 자연스러운 사용 맥락을 유지하되 노출·신체 접촉·행위 묘사를 만들지 않는다.
- 생성 파일은 로컬 IMAGE_OUTPUT_DIR에 저장한다.
- IMAGE_PUBLIC_BASE_URL이 설정되어 있으면 동일 파일명의 공개 URL도 반환한다.
"""
from __future__ import annotations

import base64
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


def _is_sensitive_product(product: dict[str, Any]) -> bool:
    """성인 전용/민감 카테고리를 보수적으로 감지한다.

    공급처가 명시적으로 제공한 adult/restricted 플래그를 최우선으로 사용하고,
    없을 때만 상품명/카테고리의 일반적인 성인 전용 표기를 보조적으로 확인한다.
    """
    for key in ("adult_only", "adult", "restricted", "minor_purchasable"):
        if key not in product:
            continue
        value = product.get(key)
        if key == "minor_purchasable" and value is False:
            return True
        if key != "minor_purchasable" and bool(value):
            return True

    haystack = " ".join(
        str(product.get(key) or "")
        for key in ("name", "category", "subcategory", "tags")
    ).lower()
    markers = (
        "성인용", "성인 전용", "19금", "19세", "adult only", "adult-only",
        "커플용품", "intimate care", "intimate product",
    )
    return any(marker in haystack for marker in markers)


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
        "이미지 내부의 긴 한국어 문장은 생성하지 말고 제품 중심 비주얼과 간단한 공간 구성 위주. "
    )

    if _is_sensitive_product(product):
        common += (
            "성인 전용 소매상품의 합법적인 전자상거래 제품 촬영 스타일로 표현한다. "
            "등장 인물이 필요하면 성인으로 명확한 완전 착의 모델 또는 성인의 손만 사용한다. "
            "노출, 신체의 민감 부위, 신체에 제품이 닿는 장면, 성적 행동이나 암시적 포즈는 만들지 않는다. "
            "제품의 외형과 실제 사용 준비 과정이 자연스럽게 이해되도록 한다. "
        )
        templates = [
            (
                "hero",
                common
                + "첫 화면용 히어로 섹션. 실제 제품과 패키지를 프리미엄 스튜디오 또는 세련된 생활공간에 자연스럽게 배치하고 제품을 크게 보여준다.",
            ),
            (
                "features",
                common
                + "핵심 특징 설명 섹션. 성인의 손이 제품을 들고 버튼, 표면, 충전부, 구성품 등 실제로 확인 가능한 요소를 자연스럽게 보여주는 확대 컷을 구성한다.",
            ),
            (
                "usage",
                common
                + "실제 사용 맥락 섹션. 성인 사용자가 완전히 옷을 입은 상태에서 제품을 개봉하거나 손에 들고 조작하고, 충전·세척·건조·보관 또는 휴대 준비를 하는 모습을 자연스럽게 보여준다. 제품은 항상 화면의 주인공이며 신체에 사용하는 장면은 표현하지 않는다.",
            ),
            (
                "detail",
                common
                + "소재·마감·디테일 섹션. 제품 표면과 버튼, 연결부, 파우치나 구성품을 손으로 확인하는 가까운 장면으로 표현하고 제품 외형을 바꾸지 않는다.",
            ),
            (
                "closing",
                common
                + "마지막 구매검토 섹션. 사용 후 정리·보관되는 현실적인 생활 장면과 제품 전체 구성을 정돈된 스튜디오 컷으로 보여준다.",
            ),
        ]
    else:
        templates = [
            ("hero", common + "첫 화면용 히어로 섹션. 제품을 크게 보여주고 사용 맥락이 직관적으로 보이는 프리미엄 구성."),
            ("features", common + "핵심 특징 설명 섹션. 실제 제품에서 시각적으로 확인 가능한 특징 2~3개를 확대 컷과 여백으로 구성."),
            ("usage", common + "실제 사용 장면 섹션. 제품 카테고리에 맞는 현실적인 사용 환경에서 제품 사용 모습을 자연스럽게 표현."),
            ("detail", common + "소재·마감·디테일을 보여주는 클로즈업 섹션. 제품 외형을 바꾸지 말 것."),
            ("closing", common + "상세페이지 마지막 구매검토 섹션. 제품 전체 구성을 정돈된 스튜디오 컷으로 다시 보여주는 마무리."),
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


def _moderation_blocked(response: httpx.Response) -> bool:
    text = response.text.lower()
    return response.status_code == 400 and (
        "moderation_blocked" in text
        or "safety_violations" in text
        or "rejected by the safety system" in text
    )


def _request_image(
    *,
    headers: dict[str, str],
    model: str,
    prompt: str,
    size: str,
    quality: str,
    ref: tuple[bytes, str] | None,
) -> httpx.Response:
    if ref:
        image_bytes, ext = ref
        mime = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg"}.get(ext, "image/jpeg")
        files = {"image": (f"reference{ext}", image_bytes, mime)}
        data = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "output_format": "png",
        }
        return httpx.post(
            "https://api.openai.com/v1/images/edits",
            headers=headers,
            data=data,
            files=files,
            timeout=180,
        )

    return httpx.post(
        "https://api.openai.com/v1/images/generations",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "model": model,
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "output_format": "png",
        },
        timeout=180,
    )


def generate_detail_images(
    product: dict[str, Any],
    *,
    count: int | None = None,
    reference_url: str = "",
) -> list[GeneratedDetailImage]:
    """OpenAI GPT Image로 상세페이지용 세로 이미지를 생성한다.

    reference_url이 있으면 `/v1/images/edits`를 사용해 제품 외형 보존을 우선한다.
    민감 카테고리는 처음부터 안전한 생활형 사용 맥락 프롬프트를 사용한다.
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
        response = _request_image(
            headers=headers,
            model=s.image_ai_model,
            prompt=prompt,
            size=s.image_ai_size,
            quality=s.image_ai_quality,
            ref=ref,
        )
        if response.status_code not in (200, 201):
            if _moderation_blocked(response):
                raise RuntimeError(
                    "AI 이미지 생성이 안전 필터에서 차단되었습니다. "
                    "결제나 API 키 문제는 아닙니다. 현재 상품/reference 조합이 이미지 안전 기준을 넘은 것으로 판단되었습니다. "
                    "AutoSellerAI는 필터 우회를 시도하지 않으며, 민감 카테고리에는 완전 착의 성인·손·개봉·조작·충전·세척·보관 중심의 생활형 사용 장면만 요청합니다. "
                    f"원본 응답: {response.text[:350]}"
                )
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
