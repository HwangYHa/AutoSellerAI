from __future__ import annotations

import ast
import base64
import io
import os
from pathlib import Path

from PIL import Image
from sqlalchemy import inspect

from app.db import _get_engine
from app.image_studio.mappings import (
    BACKGROUND_MAP,
    BODY_FRAME_MAP,
    HAIR_STYLE_MAP,
    OUTFIT_MAP,
    POSE_MAP,
    PRESETS,
    PROMPT_MAPS,
    mapping_stats,
)
from app.image_studio.models import ensure_image_studio_schema
from app.image_studio.prompt_builder import build_prompt, build_txt2img_payload
from app.image_studio.schemas import HumanImageRequest
from app.image_studio.sd_webui_client import choose_upscaler
from app.image_studio.tasks import _save_generated_images


def test_default_prompt_is_adult_photoreal_and_structured():
    req = HumanImageRequest()
    bundle = build_prompt(req)
    text = bundle.positive.lower()
    assert "adult korean woman" in text
    assert "photorealistic" in text
    assert "realistic skin texture" in text
    assert "anatomically correct body" in text
    assert "five fingers" in text
    assert "child" not in text
    assert "teen" not in text


def test_deep_focus_and_full_body_add_matching_negative_guards():
    req = HumanImageRequest(depth_of_field="배경까지 선명", shot="전신")
    negative = build_prompt(req).negative.lower()
    assert "bokeh" in negative
    assert "blurred background" in negative
    assert "cropped legs" in negative
    assert "missing feet" in negative


def test_adetailer_payload_is_only_added_when_extension_is_available():
    req = HumanImageRequest(adetailer_enabled=True)
    without = build_txt2img_payload(req, adetailer_available=False, selected_upscaler="Latent")
    assert "alwayson_scripts" not in without

    with_ad = build_txt2img_payload(req, adetailer_available=True, selected_upscaler="Latent")
    args = with_ad["alwayson_scripts"]["ADetailer"]["args"]
    assert isinstance(args, list)
    assert args[0]["ad_model"] == "face_yolov8n.pt"
    assert args[0]["ad_confidence"] == 0.3


def test_checkpoint_uses_per_request_override_not_global_options():
    req = HumanImageRequest(checkpoint="photoModel.safetensors")
    payload = build_txt2img_payload(req, adetailer_available=False, selected_upscaler="Latent")
    assert payload["override_settings"]["sd_model_checkpoint"] == "photoModel.safetensors"
    assert payload["override_settings_restore_afterwards"] is True


def test_upscaler_fallback_prefers_known_photographic_choices():
    available = ["None", "Lanczos", "Latent", "R-ESRGAN 4x+"]
    assert choose_upscaler("missing", available) == "R-ESRGAN 4x+"
    assert choose_upscaler("Lanczos", available) == "Lanczos"
    assert choose_upscaler("missing", []) is None


def test_expanded_prompt_catalog_has_real_depth_not_just_total_count():
    stats = mapping_stats()
    assert stats["total"] >= 300
    assert stats["presets"] >= 10
    assert len(PROMPT_MAPS) >= 25
    assert len(HAIR_STYLE_MAP) >= 25
    assert len(BODY_FRAME_MAP) >= 10
    assert len(OUTFIT_MAP) >= 30
    assert len(POSE_MAP) >= 20
    assert len(BACKGROUND_MAP) >= 25


def test_new_mapping_choices_validate_and_flow_into_prompt():
    req = HumanImageRequest(
        preset="프리미엄 룩북",
        hair_style="허쉬컷",
        body_frame="슬림 글래머",
        outfit="블레이저룩",
        pose="재킷 정리하기",
        background="베이지 스튜디오",
        lighting="뷰티 소프트박스",
        camera="70mm 패션",
        shot="전신",
    )
    text = build_prompt(req).positive.lower()
    assert "hush cut" in text
    assert "curvier feminine silhouette" in text
    assert "tailored blazer" in text
    assert "adjusting jacket" in text
    assert "beige photography studio" in text
    assert "softbox beauty lighting" in text
    assert "70mm fashion portrait" in text


def test_mapping_stats_matches_actual_maps_without_double_counting_presets():
    stats = mapping_stats()
    assert stats["total"] == sum(len(mapping) for mapping in PROMPT_MAPS.values())
    assert stats["presets"] == len(PRESETS)


def test_image_studio_schema_is_created_in_test_database():
    ensure_image_studio_schema()
    assert "ai_image_generations" in inspect(_get_engine()).get_table_names()


def test_generated_base64_image_is_validated_and_written(tmp_path, monkeypatch):
    image = Image.new("RGB", (16, 16), (120, 120, 120))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode()
    monkeypatch.setenv("SD_IMAGE_OUTPUT_DIR", str(tmp_path))

    paths = _save_generated_images(7, [encoded])
    assert len(paths) == 1
    target = Path(paths[0])
    assert target.exists()
    with Image.open(target) as restored:
        assert restored.size == (16, 16)


def test_ui_and_compose_expose_dedicated_image_studio_worker():
    root = Path(__file__).resolve().parents[1]
    page = (root / "gui/pages/13_AI_인물_이미지_스튜디오.py").read_text(encoding="utf-8")
    service = (root / "app/image_studio/service.py").read_text(encoding="utf-8")
    main = (root / "gui/main.py").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")

    ast.parse(page)

    assert "Stable Diffusion 이미지 생성" in page
    assert "얼굴·헤어" in page
    assert "체형" in page
    assert "의상·분위기" in page
    assert "webui-user.bat" in page
    assert "--api --listen --port 7860" in page
    assert "get_image_queue_status" in page
    assert "@st.fragment(run_every=live_interval)" in page
    assert "실시간 진행 상태" in page
    assert "같은 Seed 재생성" in page
    assert "랜덤 Seed 재생성" in page
    assert "Payload JSON 저장" in page
    assert "Worker.all(queue=queue)" in service
    assert "AI 인물 이미지 스튜디오" in main
    assert "image-worker:" in compose
    assert '"image"' in compose
    assert "host.docker.internal:7860" in compose
    assert "SD_WEBUI_DOCKER_URL" in env_example
