"""REST catalog for adult Stable Diffusion body-profile presets."""
from __future__ import annotations

from fastapi import APIRouter

from app.image_studio.body_profiles import (
    BODY_PROFILE_CONTROL_DEFAULTS,
    BODY_PROFILE_MAP,
    BUST_VOLUME_MAP,
    LEG_PROPORTION_MAP,
    MUSCLE_TONE_MAP,
    RIBCAGE_MAP,
    profile_reference_rows,
)


router = APIRouter(prefix="/image-studio", tags=["image-studio"])


@router.get("/body-profiles")
def body_profiles_catalog() -> dict:
    return {
        "profiles": list(BODY_PROFILE_MAP.keys()),
        "profile_prompts": dict(BODY_PROFILE_MAP),
        "profile_defaults": {key: dict(value) for key, value in BODY_PROFILE_CONTROL_DEFAULTS.items()},
        "reference_rows": profile_reference_rows(),
        "options": {
            "ribcage": list(RIBCAGE_MAP.keys()),
            "bust_volume": list(BUST_VOLUME_MAP.keys()),
            "muscle_tone": list(MUSCLE_TONE_MAP.keys()),
            "leg_proportion": list(LEG_PROPORTION_MAP.keys()),
        },
        "notes": [
            "모든 프로필은 성인 전용입니다.",
            "키·체중·BMI·체지방률·브라 예시는 참고 메타데이터이며 생성 목표 수치가 아닙니다.",
            "실제 Stable Diffusion 프롬프트에는 인상·실루엣·근육·흉곽·의상 핏 중심 자연어만 사용합니다.",
            "모든 기본 프롬프트는 완전 착의 상업/라이프스타일 이미지를 전제로 합니다.",
        ],
    }


__all__ = ["router"]
