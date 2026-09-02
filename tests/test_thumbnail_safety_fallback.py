from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import httpx
from PIL import Image

from app.media import thumbnail


def _png_bytes(width: int = 640, height: int = 900) -> bytes:
    image = Image.new("RGB", (width, height), (240, 240, 240))
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _settings(tmp_path: Path):
    return SimpleNamespace(
        image_ai_enabled=True,
        image_ai_provider="openai",
        openai_api_key="test-key",
        image_ai_model="gpt-image-2",
        image_thumbnail_size="1024x1024",
        image_thumbnail_quality="medium",
        image_output_dir=str(tmp_path),
    )


def test_adult_sexual_product_skips_image_api_and_uses_reference(monkeypatch, tmp_path):
    monkeypatch.setattr(thumbnail, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(thumbnail, "_download_reference", lambda _url: (_png_bytes(), ".png"))
    monkeypatch.setattr(thumbnail, "publish_generated_file", lambda path: f"https://cdn.test/{path.name}")

    def should_not_call_api(**_kwargs):
        raise AssertionError("adult sexual product must not call the generative image API")

    monkeypatch.setattr(thumbnail, "_request_image", should_not_call_api)

    result = thumbnail.generate_thumbnail(
        {
            "sku": "ADULT-1",
            "name": "여성용 진동 흡입기 바이브레이터",
            "category": "성인용품",
        },
        reference_url="https://supplier.test/original.png",
    )

    assert result.model == "local-reference-fallback"
    assert result.public_url.startswith("https://cdn.test/")
    path = Path(result.local_path)
    assert path.exists()
    with Image.open(path) as output:
        assert output.size == (1024, 1024)
        assert output.mode == "RGB"


def test_moderation_block_with_reference_falls_back_without_retrying_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(thumbnail, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(thumbnail, "_download_reference", lambda _url: (_png_bytes(800, 600), ".png"))
    monkeypatch.setattr(thumbnail, "publish_generated_file", lambda path: f"https://cdn.test/{path.name}")

    calls = []

    def blocked_request(**kwargs):
        calls.append(kwargs)
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Your request was rejected by the safety system.",
                    "code": "moderation_blocked",
                    "moderation_details": {"sexual": True},
                }
            },
            request=httpx.Request("POST", "https://api.openai.com/v1/images/edits"),
        )

    monkeypatch.setattr(thumbnail, "_request_image", blocked_request)

    result = thumbnail.generate_thumbnail(
        {"sku": "GENERIC-1", "name": "테스트 상품", "category": "생활용품"},
        reference_url="https://supplier.test/original.png",
    )

    assert len(calls) == 1
    assert result.model == "local-reference-fallback"
    assert Path(result.local_path).exists()


def test_moderation_block_without_reference_returns_safe_actionable_message(monkeypatch, tmp_path):
    monkeypatch.setattr(thumbnail, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(thumbnail, "_download_reference", lambda _url: None)

    def blocked_request(**_kwargs):
        return httpx.Response(
            400,
            json={"error": {"message": "rejected", "code": "moderation_blocked"}},
            request=httpx.Request("POST", "https://api.openai.com/v1/images/generations"),
        )

    monkeypatch.setattr(thumbnail, "_request_image", blocked_request)

    try:
        thumbnail.generate_thumbnail({"sku": "GENERIC-2", "name": "일반 상품"})
    except RuntimeError as exc:
        text = str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")

    assert "안전 정책" in text
    assert "원본 이미지를 선택" in text
    assert "원본 응답" not in text
    assert "moderation_blocked" not in text
