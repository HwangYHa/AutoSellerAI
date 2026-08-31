"""REST boundary for AutoSellerAI's Stable Diffusion image studio.

This router is mounted under Seller OS `/api/v3`, so it inherits the control-plane
Bearer token policy.  HTTP handlers never perform GPU generation synchronously;
all txt2img work is queued on the dedicated RQ `image` worker.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.image_studio.mappings import (
    AGE_MAP,
    BACKGROUND_MAP,
    BODY_FRAME_MAP,
    CAMERA_MAP,
    CHEST_PROPORTION_MAP,
    DOF_MAP,
    EXPRESSION_MAP,
    EYE_STYLE_MAP,
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
    mapping_stats,
)
from app.image_studio.prompt_builder import build_prompt, build_txt2img_payload
from app.image_studio.schemas import HumanImageRequest
from app.image_studio.sd_webui_client import StableDiffusionWebUIClient, choose_upscaler
from app.image_studio.service import (
    cancel_generation,
    create_generation,
    generation_to_dict,
    get_generation,
    get_image_queue_status,
    list_generations,
    resolve_generation_image,
    retry_generation,
)

router = APIRouter(prefix="/image-studio", tags=["image-studio"])


class RetryRequest(BaseModel):
    seed_mode: Literal["random", "same"] = "random"


def _capabilities() -> dict:
    return StableDiffusionWebUIClient().capabilities().model_dump()


def _require_ready() -> tuple[dict, dict]:
    caps = _capabilities()
    queue = get_image_queue_status()
    problems = []
    if not caps.get("ok"):
        problems.append(caps.get("error") or "Stable Diffusion WebUI 연결 실패")
    if not queue.get("ok"):
        problems.append(queue.get("error") or "Redis image queue 연결 실패")
    elif int(queue.get("workers") or 0) < 1:
        problems.append("image-worker가 실행 중이 아닙니다.")
    if problems:
        raise HTTPException(status_code=503, detail={"message": "이미지 생성 준비가 완료되지 않았습니다.", "problems": problems})
    return caps, queue


def _actual_seed(data: dict) -> int | None:
    info = data.get("response_info") or {}
    if not isinstance(info, dict):
        return None
    seeds = info.get("all_seeds")
    if isinstance(seeds, list) and seeds:
        try:
            return int(seeds[0])
        except (TypeError, ValueError):
            pass
    try:
        if info.get("seed") is not None:
            return int(info["seed"])
    except (TypeError, ValueError):
        pass
    return None


def _generation_response(row) -> dict:
    data = generation_to_dict(row)
    image_paths = data.pop("image_paths", [])
    count = len(image_paths) if isinstance(image_paths, list) else 0
    data["image_count"] = count
    data["images"] = [
        {"index": index, "url": f"/api/v3/image-studio/generations/{row.id}/images/{index}"}
        for index in range(count)
    ]
    data["actual_seed"] = _actual_seed(data)
    return jsonable_encoder(data)


@router.get("/health")
def image_studio_health() -> dict:
    caps = _capabilities()
    queue = get_image_queue_status()
    recent = list_generations(limit=20)
    active = next((row for row in recent if str(row.status) in {"running", "cancel_requested", "queued"}), None)
    progress = {}
    if caps.get("ok") and active and str(active.status) in {"running", "cancel_requested"}:
        try:
            progress = StableDiffusionWebUIClient().progress()
        except Exception as exc:
            progress = {"error": str(exc)}
    ready = bool(caps.get("ok") and queue.get("ok") and int(queue.get("workers") or 0) > 0)
    return {
        "ok": ready,
        "ready": ready,
        "webui": caps,
        "queue": queue,
        "active_generation": _generation_response(active) if active else None,
        "progress": progress,
    }


@router.get("/catalog")
def image_studio_catalog() -> dict:
    """Return UI-safe options plus live WebUI model/sampler catalogs."""
    return {
        "webui": _capabilities(),
        "presets": PRESETS,
        "mapping_stats": mapping_stats(),
        "options": {
            "gender": list(GENDER_MAP.keys()),
            "age": list(AGE_MAP.keys()),
            "hair_style": list(HAIR_STYLE_MAP.keys()),
            "hair_color": list(HAIR_COLOR_MAP.keys()),
            "face_shape": list(FACE_SHAPE_MAP.keys()),
            "eye_style": list(EYE_STYLE_MAP.keys()),
            "nose_style": list(NOSE_STYLE_MAP.keys()),
            "lip_style": list(LIP_STYLE_MAP.keys()),
            "skin_tone": list(SKIN_TONE_MAP.keys()),
            "expression": list(EXPRESSION_MAP.keys()),
            "body_frame": list(BODY_FRAME_MAP.keys()),
            "height_impression": list(HEIGHT_MAP.keys()),
            "shoulder": list(SHOULDER_MAP.keys()),
            "waist_hip": list(WAIST_HIP_MAP.keys()),
            "chest_proportion": list(CHEST_PROPORTION_MAP.keys()),
            "outfit": list(OUTFIT_MAP.keys()),
            "outfit_color": list(OUTFIT_COLOR_MAP.keys()),
            "mood": list(MOOD_MAP.keys()),
            "personality": list(PERSONALITY_MAP.keys()),
            "pose": list(POSE_MAP.keys()),
            "shot": list(SHOT_MAP.keys()),
            "background": list(BACKGROUND_MAP.keys()),
            "lighting": list(LIGHTING_MAP.keys()),
            "depth_of_field": list(DOF_MAP.keys()),
            "camera": list(CAMERA_MAP.keys()),
        },
    }


@router.post("/preview")
def preview_generation(body: HumanImageRequest) -> dict:
    """Build the exact prompt/payload without queueing or consuming GPU time."""
    bundle = build_prompt(body)
    caps = _capabilities()
    warnings: list[str] = []
    selected_upscaler = body.hr_upscaler
    adetailer_available = False
    if caps.get("ok"):
        adetailer_available = bool(caps.get("adetailer_available"))
        if body.enable_hr:
            selected_upscaler = choose_upscaler(body.hr_upscaler, caps.get("upscalers") or []) or body.hr_upscaler
        if body.adetailer_enabled and not adetailer_available:
            warnings.append("ADetailer가 WebUI에서 감지되지 않아 실제 생성 시 자동 생략됩니다.")
    else:
        warnings.append("WebUI가 오프라인이므로 설치 capability를 반영하지 않은 미리보기입니다.")

    payload = build_txt2img_payload(
        body,
        adetailer_available=adetailer_available,
        selected_upscaler=selected_upscaler,
    )
    final_width = int(round(body.width * body.hr_scale)) if body.enable_hr else body.width
    final_height = int(round(body.height * body.hr_scale)) if body.enable_hr else body.height
    return {
        "subject_summary": bundle.subject_summary,
        "positive_prompt": bundle.positive,
        "negative_prompt": bundle.negative,
        "payload": payload,
        "estimated_output": {"width": final_width, "height": final_height, "images": body.batch_size},
        "warnings": warnings,
        "webui_online": bool(caps.get("ok")),
    }


@router.post("/generations", status_code=status.HTTP_202_ACCEPTED)
def queue_generation(body: HumanImageRequest) -> dict:
    caps, queue = _require_ready()
    try:
        row = create_generation(body)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "accepted": True,
        "generation": _generation_response(row),
        "runtime": {"webui_model": caps.get("model") or "", "workers": queue.get("workers", 0)},
    }


@router.get("/generations")
def generations(
    limit: int = Query(default=50, ge=1, le=300),
    generation_status: str = Query(default="", alias="status"),
) -> dict:
    rows = list_generations(limit=limit, status=generation_status)
    return {"items": [_generation_response(row) for row in rows], "count": len(rows)}


@router.get("/generations/{generation_id}")
def generation(generation_id: int) -> dict:
    row = get_generation(generation_id)
    if not row:
        raise HTTPException(status_code=404, detail="이미지 생성 작업을 찾을 수 없습니다.")
    return _generation_response(row)


@router.get("/generations/{generation_id}/images/{image_index}")
def generation_image(generation_id: int, image_index: int):
    try:
        path = resolve_generation_image(generation_id, image_index)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (IndexError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileResponse(path=str(path), media_type="image/png", filename=path.name)


@router.post("/generations/{generation_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry(generation_id: int, body: RetryRequest) -> dict:
    _require_ready()
    try:
        row = retry_generation(generation_id, same_seed=body.seed_mode == "same")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"accepted": True, "source_generation_id": generation_id, "generation": _generation_response(row)}


@router.post("/generations/{generation_id}/cancel")
def cancel(generation_id: int) -> dict:
    try:
        result = cancel_generation(generation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result)
    return result


@router.get("/progress")
def webui_progress() -> dict:
    try:
        return StableDiffusionWebUIClient().progress()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


__all__ = ["router"]
