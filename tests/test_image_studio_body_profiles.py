from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from app.image_studio.body_profile_reference import BODY_PROFILE_EXTENDED_REFERENCE
from app.image_studio.body_profiles import BODY_PROFILE_CONTROL_DEFAULTS, BODY_PROFILE_MAP
from app.image_studio.prompt_builder import build_prompt, resolved_body_profile
from app.image_studio.schemas import HumanImageRequest
from app.os.api import app


client = TestClient(app)
EXPECTED = ["매우 슬림", "슬림", "슬림 글래머", "균형형", "볼륨형", "운동형"]


def test_six_operator_body_profiles_are_preserved_in_order():
    assert list(BODY_PROFILE_MAP) == EXPECTED
    assert set(BODY_PROFILE_CONTROL_DEFAULTS) == set(EXPECTED)
    assert set(BODY_PROFILE_EXTENDED_REFERENCE) == set(EXPECTED)


def test_legacy_body_frame_infers_new_profile_without_ui_changes():
    assert resolved_body_profile(HumanImageRequest(body_frame="매우 슬림")) == "매우 슬림"
    assert resolved_body_profile(HumanImageRequest(body_frame="슬림 글래머")) == "슬림 글래머"
    assert resolved_body_profile(HumanImageRequest(body_frame="볼륨형")) == "볼륨형"
    assert resolved_body_profile(HumanImageRequest(body_frame="애슬레틱")) == "운동형"


def test_explicit_profile_and_granular_controls_flow_into_prompt():
    req = HumanImageRequest(
        body_profile="슬림 글래머", body_frame="슬림 글래머", ribcage="좁음",
        bust_volume="보통~큰 편", muscle_tone="보통·부드러움",
        leg_proportion="약간 긴 편", shot="전신",
    )
    bundle = build_prompt(req)
    positive = bundle.positive.lower()
    negative = bundle.negative.lower()
    assert "narrow ribcage" in positive
    assert "moderate-to-full natural bust volume" in positive
    assert "moderate natural muscle tone" in positive
    assert "slightly long-looking legs" in positive
    assert "fully clothed adult commercial fashion/lifestyle presentation" in positive
    assert "extreme hourglass" in negative


def test_numeric_reference_metadata_never_becomes_generation_prompt():
    req = HumanImageRequest(body_profile="슬림 글래머", body_frame="슬림 글래머")
    text = build_prompt(req).positive
    for forbidden in ("49~53kg", "18.5~19.5", "22~24%", "70cm", "70C", "0.68"):
        assert forbidden not in text


def test_athletic_profile_has_anti_exaggeration_guard():
    req = HumanImageRequest(body_profile="운동형", body_frame="애슬레틱")
    negative = build_prompt(req).negative.lower()
    assert "bodybuilder physique" in negative
    assert "extreme muscle mass" in negative


def test_female_specific_reference_does_not_leak_into_male_prompt():
    req = HumanImageRequest(gender="남성", body_frame="애슬레틱", bust_volume="큼", ribcage="넓은 편")
    positive = build_prompt(req).positive.lower()
    assert "feminine silhouette" not in positive
    assert "bust volume" not in positive
    assert "full natural bust" not in positive
    assert "adult korean man" in positive


def test_every_profile_default_combination_validates():
    for profile, defaults in BODY_PROFILE_CONTROL_DEFAULTS.items():
        req = HumanImageRequest(body_profile=profile, **defaults)
        assert req.body_profile == profile
        assert build_prompt(req).positive


def test_extended_reference_preserves_clothing_and_shape_rows():
    slim_glamour = BODY_PROFILE_EXTENDED_REFERENCE["슬림 글래머"]
    assert slim_glamour["bust_projection"]
    assert slim_glamour["upper_lower_volume"]
    assert slim_glamour["natural_shape"]
    assert slim_glamour["tshirt_fit"]
    assert slim_glamour["knit_fit"]
    assert slim_glamour["dress_fit"]
    assert slim_glamour["visual_emphasis_factors"]
    assert slim_glamour["sd_phrase_reference"]


def test_body_profile_api_is_mounted_and_returns_reference_metadata():
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/v3/image-studio/body-profiles" in paths
    response = client.get("/api/v3/image-studio/body-profiles")
    assert response.status_code == 200
    body = response.json()
    assert body["profiles"] == EXPECTED
    assert body["extended_reference"]["볼륨형"]["tshirt_fit"]
    assert body["profile_defaults"]["운동형"]["muscle_tone"] == "높음·탄탄한 코어"


def test_body_profile_streamlit_page_is_valid_and_linked():
    root = Path(__file__).resolve().parents[1]
    page = (root / "gui/pages/16_AI_체형_프리셋.py").read_text(encoding="utf-8")
    main = (root / "gui/main.py").read_text(encoding="utf-8")
    ast.parse(page)
    assert "매우 슬림 · 슬림 · 슬림 글래머 · 균형형 · 볼륨형 · 운동형" in page
    assert "누락 없이 보존된 상세 참고표" in page
    assert "이 프로필 권장값 적용" in page
    assert "이 체형으로 이미지 생성" in page
    assert "16_AI_체형_프리셋.py" in main
