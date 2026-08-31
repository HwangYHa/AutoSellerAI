"""Prompt construction for the Stable Diffusion human image studio."""
from __future__ import annotations

import re

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
    SHOULDER_MAP,
    SHOT_MAP,
    SKIN_TONE_MAP,
    WAIST_HIP_MAP,
    EYE_STYLE_MAP,
)
from app.image_studio.schemas import HumanImageRequest, PromptBundle


QUALITY_BLOCK = (
    "photorealistic professional photography, realistic adult human anatomy, "
    "natural Korean facial features, realistic skin texture with visible pores and subtle imperfections, "
    "natural hair strands, realistic fabric texture, physically plausible lighting, "
    "balanced color science, high micro-detail, clean composition"
)

ANATOMY_BLOCK = (
    "anatomically correct body, natural joints, realistic hands, five fingers on each visible hand, "
    "natural posture, realistic limb proportions, symmetrical coherent facial structure"
)

BASE_NEGATIVE = (
    "worst quality, low quality, lowres, blurry, motion blur, jpeg artifacts, oversharpened, "
    "bad anatomy, bad proportions, deformed body, malformed limbs, extra limbs, duplicated limbs, "
    "bad hands, malformed hands, extra fingers, missing fingers, fused fingers, six fingers, four fingers, "
    "deformed face, distorted face, asymmetrical eyes, cross-eyed, duplicate person, cloned face, "
    "unnatural skin, plastic skin, waxy skin, excessive beauty filter, uncanny face, "
    "cropped head, cropped feet, out of frame, text, watermark, logo, signature, "
    "cartoon, anime, illustration, painting, 3d render, cgi, doll"
)


def _clean_fragment(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value


def _join(*parts: str) -> str:
    return ", ".join(part for part in (_clean_fragment(x) for x in parts) if part)


def build_prompt(req: HumanImageRequest) -> PromptBundle:
    subject = _join(
        "one person",
        GENDER_MAP[req.gender],
        AGE_MAP[req.age],
    )

    appearance = _join(
        HAIR_STYLE_MAP[req.hair_style],
        HAIR_COLOR_MAP[req.hair_color],
        FACE_SHAPE_MAP[req.face_shape],
        EYE_STYLE_MAP[req.eye_style],
        NOSE_STYLE_MAP[req.nose_style],
        LIP_STYLE_MAP[req.lip_style],
        SKIN_TONE_MAP[req.skin_tone],
        EXPRESSION_MAP[req.expression],
    )

    body = _join(
        BODY_FRAME_MAP[req.body_frame],
        HEIGHT_MAP[req.height_impression],
        SHOULDER_MAP[req.shoulder],
        WAIST_HIP_MAP[req.waist_hip],
        CHEST_PROPORTION_MAP[req.chest_proportion],
    )

    styling = _join(
        OUTFIT_MAP[req.outfit],
        OUTFIT_COLOR_MAP[req.outfit_color],
        MOOD_MAP[req.mood],
        PERSONALITY_MAP[req.personality],
    )

    scene = _join(
        POSE_MAP[req.pose],
        SHOT_MAP[req.shot],
        BACKGROUND_MAP[req.background],
        LIGHTING_MAP[req.lighting],
        DOF_MAP[req.depth_of_field],
        CAMERA_MAP[req.camera],
        "sharp primary subject focus",
        "realistic shadows and reflections",
    )

    positive = _join(
        QUALITY_BLOCK,
        subject,
        appearance,
        body,
        styling,
        scene,
        ANATOMY_BLOCK,
        req.custom_positive,
    )

    negative_parts = [BASE_NEGATIVE]
    if req.depth_of_field == "배경까지 선명":
        negative_parts.append("bokeh, extreme shallow depth of field, blurred background")
    if req.shot == "전신":
        negative_parts.append("cropped legs, cropped shoes, missing feet")
    if req.pose == "상품을 들고 있기":
        negative_parts.append("floating object, object fused with hand, fingers through object")
    if req.custom_negative:
        negative_parts.append(req.custom_negative)

    negative = _join(*negative_parts)
    summary = f"{req.gender} · {req.age} · {req.body_frame} · {req.outfit} · {req.background} · {req.shot}"
    return PromptBundle(positive=positive, negative=negative, subject_summary=summary)


def build_txt2img_payload(
    req: HumanImageRequest,
    *,
    adetailer_available: bool,
    selected_upscaler: str | None = None,
) -> dict:
    bundle = build_prompt(req)
    payload: dict = {
        "prompt": bundle.positive,
        "negative_prompt": bundle.negative,
        "steps": req.steps,
        "sampler_name": req.sampler_name,
        "scheduler": req.scheduler,
        "cfg_scale": req.cfg_scale,
        "width": req.width,
        "height": req.height,
        "seed": req.seed,
        "batch_size": req.batch_size,
        "n_iter": 1,
        "restore_faces": False,
        "tiling": False,
        "send_images": True,
        "save_images": False,
        "enable_hr": bool(req.enable_hr),
    }

    if req.enable_hr:
        payload.update(
            {
                "hr_scale": req.hr_scale,
                "hr_upscaler": selected_upscaler or req.hr_upscaler,
                "hr_second_pass_steps": req.hr_second_pass_steps,
                "denoising_strength": req.denoising_strength,
            }
        )

    if req.checkpoint:
        # Per-request override avoids changing the global checkpoint for other jobs.
        payload["override_settings"] = {"sd_model_checkpoint": req.checkpoint}
        payload["override_settings_restore_afterwards"] = True

    if req.adetailer_enabled and adetailer_available:
        # Current ADetailer REST API accepts a minimal dict per model.  Omitted
        # fields use ADetailer's defaults, reducing breakage across extension versions.
        payload["alwayson_scripts"] = {
            "ADetailer": {
                "args": [
                    {
                        "ad_model": req.adetailer_model,
                        "ad_confidence": req.adetailer_confidence,
                        "ad_denoising_strength": req.adetailer_denoising_strength,
                        "ad_inpaint_only_masked": True,
                        "ad_mask_blur": 4,
                        "ad_prompt": "realistic detailed adult face, natural skin texture, coherent eyes, natural lips",
                        "ad_negative_prompt": "distorted face, asymmetrical eyes, plastic skin, overprocessed face",
                    }
                ]
            }
        }

    return payload


__all__ = ["build_prompt", "build_txt2img_payload"]
