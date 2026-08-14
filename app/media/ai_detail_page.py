"""선택형 AI 상세페이지 이미지 생성.

원칙:
- 공급처 원본 이미지는 제품 정체성(reference) 확인용으로만 사용한다.
- 원본의 배경, 구도, 텍스트, 그래픽은 복제하지 않고 완전히 새로운 장면을 만든다.
- AI 생성은 사용자가 명시적으로 요청했을 때만 실행한다.
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
    """각 섹션이 서로 다른 사진이 되도록 장면·구도·행동까지 지정한다."""
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
        "한국 온라인 쇼핑몰용 세로형 프리미엄 제품 사진. "
        f"확인된 상품 정보: {fact_text}. "
        "확인되지 않은 기능, 인증, 성능 수치, 소재, 구성품, 브랜드 정보는 임의로 추가하지 말 것. "
        "REFERENCE IMAGE RULE: reference 이미지는 오직 제품 자체의 외형, 비율, 색상, 재질, 버튼과 구조를 확인하기 위한 참고자료다. "
        "reference 이미지의 배경, 카메라 각도, 제품 배치, 그림자, 텍스트, 로고 배치용 그래픽, 진동선/효과선, 장식 요소를 복제하거나 따라 하지 말 것. "
        "반드시 새로운 장소, 새로운 카메라 각도, 새로운 조명, 새로운 소품 배치로 다시 촬영한 것처럼 생성할 것. "
        "제품의 형태와 색상은 유지하되 원본 사진 자체를 편집한 것처럼 보이면 실패다. "
        "이미지 안에 상품명, 광고문구, 긴 한국어 텍스트, 임의의 브랜드명, 가짜 스펙을 생성하지 말 것. "
        "실제 전자상거래 사진작가가 촬영한 듯한 자연스러운 소재감, 현실적인 그림자, 정확한 원근감, 고급 제품사진 품질. "
        "과한 3D 렌더 느낌, 공중에 떠 있는 제품, 광고용 진동선, 비현실적 광택, 과도한 네온 효과는 금지. "
    )

    sensitive = _is_sensitive_product(product)
    if sensitive:
        common += (
            "성인 전용 소매상품의 합법적인 전자상거래 촬영이다. "
            "사람이 필요하면 성인으로 명확한 완전 착의 모델 또는 성인의 손만 표현한다. "
            "노출, 민감 부위, 제품의 신체 접촉, 성행위, 성적 포즈는 표현하지 않는다. "
            "대신 실제 구매자가 제품을 개봉하고, 손에 들고, 버튼을 확인하고, 충전·세척·보관하는 현실적인 사용 맥락을 보여준다. "
        )

    if sensitive:
        templates = [
            (
                "hero",
                common
                + "HERO SCENE: 원본과 완전히 다른 밝고 세련된 침실 드레서 또는 프리미엄 라이프스타일 공간. "
                  "제품을 천이나 트레이 위에 자연스럽게 놓고 35mm 카메라의 3/4 측면 앵글로 촬영. "
                  "부드러운 창가 자연광과 보조 조명. 제품이 화면의 약 55~65%를 차지하며 텍스트는 전혀 넣지 않는다.",
            ),
            (
                "features",
                common
                + "FEATURES SCENE: 성인의 한 손이 제품을 자연스럽게 들고 다른 손가락이 실제 버튼 또는 충전부를 가리키는 장면. "
                  "손과 제품만 프레임에 들어오며 상체나 신체는 강조하지 않는다. "
                  "50mm 렌즈 느낌의 가까운 촬영, 밝은 중성 배경, 제품 표면과 버튼 디테일이 선명하게 보이게 한다.",
            ),
            (
                "usage",
                common
                + "USAGE SCENE: 완전히 옷을 입은 성인 사용자가 침실이나 욕실의 일반적인 생활공간에서 제품을 개봉하고 손에 들어 조작 방법을 확인하는 자연스러운 순간. "
                  "제품을 신체에 사용하는 장면은 절대 보여주지 않는다. "
                  "사람은 생활 장면의 일부이고 제품이 시각적 주인공이다. 과장된 포즈 없이 다큐멘터리형 라이프스타일 사진처럼 표현한다.",
            ),
            (
                "detail",
                common
                + "DETAIL SCENE: 완전히 새로운 밝은 매크로 촬영. 제품의 실리콘/플라스틱 표면, 연결부, 버튼, 마감의 질감을 실제 사진처럼 확대한다. "
                  "원본과 다른 방향으로 제품을 회전시키고, 한쪽에는 손가락이 크기 비교용으로 자연스럽게 닿아 있어도 되지만 사용 장면은 아니다.",
            ),
            (
                "closing",
                common
                + "CLOSING SCENE: 사용 전후 정리 맥락을 보여주는 차분한 보관 장면. 제품이 파우치, 충전 케이블 또는 확인된 구성품과 함께 협탁 서랍이나 수납 트레이에 정돈되어 있다. "
                  "따뜻한 생활조명, 현실적인 공간감, 사람은 없어도 된다. 텍스트 없이 사진만 구성한다.",
            ),
        ]
    else:
        templates = [
            (
                "hero",
                common
                + "HERO SCENE: 원본과 완전히 다른 프리미엄 생활공간 또는 스튜디오 세트에서 제품을 3/4 측면 앵글로 크게 촬영. 텍스트 없이 제품과 공간만으로 첫 화면을 구성한다.",
            ),
            (
                "features",
                common
                + "FEATURES SCENE: 손으로 제품을 들거나 실제 기능 부위를 가리키는 자연스러운 가까운 장면. 원본과 다른 배경과 카메라 각도를 사용한다.",
            ),
            (
                "usage",
                common
                + "USAGE SCENE: 해당 제품을 실제 생활환경에서 사용하는 자연스러운 순간을 새로운 구도와 공간에서 촬영한다. 사람이 등장해도 제품이 주인공이어야 한다.",
            ),
            (
                "detail",
                common
                + "DETAIL SCENE: 소재, 마감, 버튼, 연결부 등 실제로 보이는 디테일을 매크로 촬영한다. 제품을 원본과 다른 방향으로 돌려 보여준다.",
            ),
            (
                "closing",
                common
                + "CLOSING SCENE: 제품과 실제 구성품을 현실적인 수납/사용 공간에 정돈해 놓은 마무리 사진. 원본 배경과 구도를 재사용하지 않는다.",
            ),
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
            "input_fidelity": "high",
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
    """OpenAI GPT Image로 서로 다른 상세페이지 장면을 생성한다."""
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
                    "민감 카테고리는 완전 착의 성인·손·개봉·조작·충전·세척·보관 중심의 생활형 사용 장면만 생성합니다. "
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
