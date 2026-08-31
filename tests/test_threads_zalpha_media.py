from __future__ import annotations

from pathlib import Path

import pytest

from app.social.threads.media import (
    media_base_is_public,
    save_threads_image,
    threads_media_public_url,
)
from app.social.threads.zalpa_content import style_threads_body


def test_zalpha_style_adds_current_social_marker_and_keeps_one_cta_keyword():
    body = (
        "솔직히 이런 제품은 딱 봤을 때 취향 맞으면 괜히 한 번 더 보게 되지 않아?\n\n"
        "디자인이 내 상황이랑 맞는지 보는 게 중요할 것 같아.\n\n"
        "궁금한 포인트 있으면 댓글에 '테스트훅' 남겨줘."
    )
    styled = style_threads_body(body, "테스트훅", tone="zalpa", seed_context="fixed")

    assert len(styled) <= 500
    assert styled.count("테스트훅") == 1
    assert any(marker in styled for marker in ("감다살", "이왜진", "ㄹㅇ", "걍", "은근", "ㅋㅋ", "영크크", "나만 아님"))


def test_zalpha_style_removes_automated_stale_meme_template():
    styled = style_threads_body(
        "어쩔티비 머선129 같은 말만 쓰는 광고는 싫어.\n\n댓글에 '포인트훅' 남겨줘.",
        "포인트훅",
        tone="zalpa",
        seed_context="stale",
    )
    assert "어쩔티비" not in styled
    assert "머선129" not in styled


def test_uploaded_threads_image_is_content_addressed_and_public_url_is_built(monkeypatch, tmp_path):
    monkeypatch.setenv("THREADS_MEDIA_DIR", str(tmp_path / "threads-media"))
    monkeypatch.setenv("THREADS_MEDIA_PUBLIC_BASE_URL", "https://media.example.com")
    jpeg = b"\xff\xd8\xff" + b"image-bytes"

    name = save_threads_image("photo.jpg", jpeg, "image/jpeg")
    stored = tmp_path / "threads-media" / name

    assert stored.read_bytes() == jpeg
    assert name.startswith("threads-") and name.endswith(".jpg")
    assert threads_media_public_url(name) == f"https://media.example.com/media/threads/{name}"
    assert media_base_is_public() is True


def test_uploaded_threads_image_rejects_disguised_or_private_media(monkeypatch, tmp_path):
    monkeypatch.setenv("THREADS_MEDIA_DIR", str(tmp_path / "threads-media"))
    monkeypatch.setenv("THREADS_MEDIA_PUBLIC_BASE_URL", "http://localhost:8000")

    with pytest.raises(ValueError):
        save_threads_image("fake.jpg", b"not-an-image", "image/jpeg")
    with pytest.raises(ValueError):
        save_threads_image("fake.png", b"\xff\xd8\xffpayload", "image/png")
    assert media_base_is_public() is False


def test_social_api_mounts_threads_media_route():
    from app.social.threads.api import app

    assert any(getattr(route, "path", "") == "/media/threads" for route in app.routes)


def test_growth_ui_exposes_tone_selector_and_photo_uploader():
    root = Path(__file__).resolve().parents[1]
    page = (root / "gui/pages/11_Threads_Growth_Automation.py").read_text(encoding="utf-8")

    assert "TONE_LABELS" in page
    assert "2026 잘파/MZ" in page
    assert "st.file_uploader" in page
    assert "save_threads_image" in page
    assert 'media_type="IMAGE"' not in page  # media type is selected dynamically, not hardcoded for every post.
    assert 'media_type=media_type' in page
