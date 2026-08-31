from __future__ import annotations

import base64
import io
import json
import os
from datetime import datetime
from pathlib import Path

from PIL import Image

from app.db import get_db
from app.image_studio.models import AIImageGeneration, ensure_image_studio_schema
from app.image_studio.prompt_builder import build_prompt, build_txt2img_payload
from app.image_studio.schemas import HumanImageRequest
from app.image_studio.sd_webui_client import StableDiffusionWebUIClient, choose_upscaler
from app.sqlite_runtime import retry_sqlite_write


def _output_root() -> Path:
    return Path(os.getenv("SD_IMAGE_OUTPUT_DIR", "data/generated/stable_diffusion")).expanduser().resolve()


def _decode_image(value: str) -> bytes:
    raw = str(value or "")
    if "," in raw and raw.lower().startswith("data:image"):
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw, validate=False)


def _save_generated_images(record_id: int, encoded_images: list[str]) -> list[str]:
    day_dir = _output_root() / datetime.utcnow().strftime("%Y%m%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    result: list[str] = []

    for index, encoded in enumerate(encoded_images, start=1):
        payload = _decode_image(encoded)
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            rgb = image.convert("RGB") if image.mode not in {"RGB", "RGBA"} else image.copy()
            target = day_dir / f"sd-{record_id:08d}-{index:02d}.png"
            rgb.save(target, format="PNG", optimize=True)
        result.append(str(target))
    return result


def _delete_generated_images(paths: list[str]) -> None:
    for value in paths:
        try:
            Path(value).unlink(missing_ok=True)
        except Exception:
            pass


def _update_record(record_id: int, **values) -> None:
    def update() -> None:
        with get_db() as db:
            row = db.get(AIImageGeneration, record_id)
            if not row:
                return
            for key, value in values.items():
                setattr(row, key, value)
            db.commit()

    retry_sqlite_write(update, attempts=6)


def _record_status(record_id: int) -> str:
    with get_db() as db:
        row = db.get(AIImageGeneration, int(record_id))
        return str(row.status or "") if row else ""


def _finish_cancelled(record_id: int, warnings: list[str]) -> dict:
    _update_record(
        record_id,
        status="cancelled",
        error="",
        image_paths_json="[]",
        warnings_json=json.dumps(warnings, ensure_ascii=False),
        completed_at=datetime.utcnow(),
    )
    return {"ok": False, "cancelled": True, "generation_id": record_id, "warnings": warnings}


def run_generation_job(record_id: int) -> dict:
    """RQ worker entrypoint. Generate, validate, store images and persist metadata."""
    ensure_image_studio_schema()
    with get_db() as db:
        row = db.get(AIImageGeneration, int(record_id))
        if not row:
            raise LookupError(f"AI image generation #{record_id} not found")
        request_json = row.request_json
        initial_status = str(row.status or "")

    if initial_status in {"cancel_requested", "cancelled"}:
        return _finish_cancelled(record_id, [])

    req = HumanImageRequest.model_validate_json(request_json)
    _update_record(record_id, status="running", started_at=datetime.utcnow(), error="")

    warnings: list[str] = []
    try:
        client = StableDiffusionWebUIClient()
        caps = client.capabilities()
        if not caps.ok:
            raise RuntimeError(caps.error or "Stable Diffusion WebUI capability check failed")

        if _record_status(record_id) == "cancel_requested":
            return _finish_cancelled(record_id, warnings)

        updates = {}
        if caps.samplers and req.sampler_name not in caps.samplers:
            fallback = next((x for x in caps.samplers if x.lower() == "dpm++ 2m"), caps.samplers[0])
            warnings.append(f"샘플러 '{req.sampler_name}' 미설치 → '{fallback}' 사용")
            updates["sampler_name"] = fallback
        if caps.schedulers and req.scheduler not in caps.schedulers:
            fallback = next((x for x in caps.schedulers if x.lower() == "karras"), caps.schedulers[0])
            warnings.append(f"스케줄러 '{req.scheduler}' 미설치 → '{fallback}' 사용")
            updates["scheduler"] = fallback
        if req.checkpoint and caps.checkpoints and req.checkpoint not in caps.checkpoints:
            warnings.append("선택한 체크포인트를 WebUI에서 찾지 못해 현재 체크포인트를 사용합니다.")
            updates["checkpoint"] = ""
        if req.adetailer_enabled and not caps.adetailer_available:
            warnings.append("ADetailer가 설치/활성화되어 있지 않아 얼굴 보정 없이 생성했습니다.")

        selected_upscaler = None
        if req.enable_hr:
            selected_upscaler = choose_upscaler(req.hr_upscaler, caps.upscalers)
            if not selected_upscaler:
                warnings.append("WebUI에서 사용 가능한 업스케일러를 찾지 못해 Hires.fix를 비활성화했습니다.")
                updates["enable_hr"] = False
            elif selected_upscaler != req.hr_upscaler:
                warnings.append(f"업스케일러 '{req.hr_upscaler}' 미설치 → '{selected_upscaler}' 사용")

        effective_req = req.model_copy(update=updates) if updates else req
        bundle = build_prompt(effective_req)
        payload = build_txt2img_payload(
            effective_req,
            adetailer_available=caps.adetailer_available,
            selected_upscaler=selected_upscaler,
        )
        _update_record(
            record_id,
            prompt=bundle.positive,
            negative_prompt=bundle.negative,
            payload_json=json.dumps(payload, ensure_ascii=False),
            warnings_json=json.dumps(warnings, ensure_ascii=False),
        )

        if _record_status(record_id) == "cancel_requested":
            return _finish_cancelled(record_id, warnings)

        response = client.txt2img(payload)
        if _record_status(record_id) == "cancel_requested":
            return _finish_cancelled(record_id, warnings)

        image_paths = _save_generated_images(record_id, response.get("images", []))
        if not image_paths:
            raise RuntimeError("Stable Diffusion WebUI가 생성 이미지를 반환하지 않았습니다.")

        # Close the tiny race where a cancel arrives after WebUI responded but
        # before DB completion is committed. Do not leave orphan PNGs behind.
        if _record_status(record_id) == "cancel_requested":
            _delete_generated_images(image_paths)
            return _finish_cancelled(record_id, warnings)

        raw_info = response.get("info", {})
        if isinstance(raw_info, str):
            try:
                info = json.loads(raw_info)
            except Exception:
                info = {"raw": raw_info[:8000]}
        elif isinstance(raw_info, dict):
            info = raw_info
        else:
            info = {"raw": raw_info}

        _update_record(
            record_id,
            status="completed",
            response_info_json=json.dumps(info, ensure_ascii=False, default=str),
            image_paths_json=json.dumps(image_paths, ensure_ascii=False),
            warnings_json=json.dumps(warnings, ensure_ascii=False),
            completed_at=datetime.utcnow(),
        )
        return {"ok": True, "generation_id": record_id, "images": image_paths, "warnings": warnings}
    except Exception as exc:
        if _record_status(record_id) == "cancel_requested":
            return _finish_cancelled(record_id, warnings)
        _update_record(
            record_id,
            status="failed",
            error=str(exc)[:4000],
            warnings_json=json.dumps(warnings, ensure_ascii=False),
            completed_at=datetime.utcnow(),
        )
        raise


__all__ = ["run_generation_job"]
