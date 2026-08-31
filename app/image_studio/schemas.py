from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.image_studio.mappings import (
    AGE_MAP,
    BACKGROUND_MAP,
    BODY_FRAME_MAP,
    CAMERA_MAP,
    CHEST_PROPORTION_MAP,
    DOF_MAP,
    EXPRESSION_MAP,
    FACE_SHAPE_MAP,
    GENDER_MAP,
    HAIR_COLOR_MAP,
    HAIR_STYLE_MAP,
    HEIGHT_MAP,
    LIGHTING_MAP,
    LIP_STYLE_MAP,
    MOOD_MAP,
    NOSE_STYLE_MAP,
    OUTFIT_COLOR_MAP,
    OUTFIT_MAP,
    PERSONALITY_MAP,
    POSE_MAP,
    PRESETS,
    SHOULDER_MAP,
    SHOT_MAP,
    SKIN_TONE_MAP,
    WAIST_HIP_MAP,
    EYE_STYLE_MAP,
)


class HumanImageRequest(BaseModel):
    """UI-safe generation request.

    All age choices are adults.  Free-form prompt fields are optional additions,
    not replacements for the structured prompt, so the app can preserve a stable
    quality baseline.
    """

    preset: str = "실사 인플루언서"
    gender: str = "여성"
    age: str = "20대 후반"

    hair_style: str = "긴 웨이브"
    hair_color: str = "다크브라운"
    face_shape: str = "계란형"
    eye_style: str = "자연스러운 눈매"
    nose_style: str = "자연스러운 코"
    lip_style: str = "자연스러운 입술"
    skin_tone: str = "내추럴"
    expression: str = "은은한 미소"

    body_frame: str = "균형형"
    height_impression: str = "평균적인 인상"
    shoulder: str = "균형 잡힌 어깨"
    waist_hip: str = "균형형"
    chest_proportion: str = "자연스러운 비율"

    outfit: str = "데일리 캐주얼"
    outfit_color: str = "자동/자연스럽게"
    mood: str = "자연스러움"
    personality: str = "밝고 친근함"
    pose: str = "카메라 바라보기"

    shot: str = "상반신"
    background: str = "감성 카페"
    lighting: str = "창가 자연광"
    depth_of_field: str = "자연스러운 심도"
    camera: str = "50mm 자연 인물"

    custom_positive: str = Field(default="", max_length=1200)
    custom_negative: str = Field(default="", max_length=1200)

    width: int = Field(default=768, ge=384, le=1536)
    height: int = Field(default=1152, ge=384, le=2048)
    steps: int = Field(default=30, ge=10, le=80)
    cfg_scale: float = Field(default=6.0, ge=1.0, le=20.0)
    sampler_name: str = "DPM++ 2M"
    scheduler: str = "Karras"
    seed: int = Field(default=-1, ge=-1, le=2_147_483_647)
    batch_size: int = Field(default=1, ge=1, le=4)

    enable_hr: bool = True
    hr_scale: float = Field(default=1.5, ge=1.0, le=2.0)
    hr_upscaler: str = "R-ESRGAN 4x+"
    hr_second_pass_steps: int = Field(default=10, ge=0, le=40)
    denoising_strength: float = Field(default=0.32, ge=0.0, le=1.0)

    adetailer_enabled: bool = True
    adetailer_model: str = "face_yolov8n.pt"
    adetailer_confidence: float = Field(default=0.3, ge=0.05, le=0.95)
    adetailer_denoising_strength: float = Field(default=0.32, ge=0.0, le=1.0)

    checkpoint: str = ""

    @field_validator(
        "preset", "gender", "age", "hair_style", "hair_color", "face_shape",
        "eye_style", "nose_style", "lip_style", "skin_tone", "expression",
        "body_frame", "height_impression", "shoulder", "waist_hip",
        "chest_proportion", "outfit", "outfit_color", "mood", "personality",
        "pose", "shot", "background", "lighting", "depth_of_field", "camera",
    )
    @classmethod
    def validate_choice(cls, value: str, info):
        mapping_by_field = {
            "preset": PRESETS,
            "gender": GENDER_MAP,
            "age": AGE_MAP,
            "hair_style": HAIR_STYLE_MAP,
            "hair_color": HAIR_COLOR_MAP,
            "face_shape": FACE_SHAPE_MAP,
            "eye_style": EYE_STYLE_MAP,
            "nose_style": NOSE_STYLE_MAP,
            "lip_style": LIP_STYLE_MAP,
            "skin_tone": SKIN_TONE_MAP,
            "expression": EXPRESSION_MAP,
            "body_frame": BODY_FRAME_MAP,
            "height_impression": HEIGHT_MAP,
            "shoulder": SHOULDER_MAP,
            "waist_hip": WAIST_HIP_MAP,
            "chest_proportion": CHEST_PROPORTION_MAP,
            "outfit": OUTFIT_MAP,
            "outfit_color": OUTFIT_COLOR_MAP,
            "mood": MOOD_MAP,
            "personality": PERSONALITY_MAP,
            "pose": POSE_MAP,
            "shot": SHOT_MAP,
            "background": BACKGROUND_MAP,
            "lighting": LIGHTING_MAP,
            "depth_of_field": DOF_MAP,
            "camera": CAMERA_MAP,
        }
        mapping = mapping_by_field[info.field_name]
        if value not in mapping:
            raise ValueError(f"unsupported {info.field_name}: {value}")
        return value

    @field_validator("custom_positive", "custom_negative", "checkpoint", "sampler_name", "scheduler", "hr_upscaler")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return str(value or "").strip()


class PromptBundle(BaseModel):
    positive: str
    negative: str
    subject_summary: str


class WebUICapabilities(BaseModel):
    ok: bool = False
    base_url: str = ""
    model: str = ""
    samplers: list[str] = Field(default_factory=list)
    schedulers: list[str] = Field(default_factory=list)
    upscalers: list[str] = Field(default_factory=list)
    txt2img_scripts: list[str] = Field(default_factory=list)
    checkpoints: list[str] = Field(default_factory=list)
    adetailer_available: bool = False
    error: str = ""


__all__ = ["HumanImageRequest", "PromptBundle", "WebUICapabilities"]
