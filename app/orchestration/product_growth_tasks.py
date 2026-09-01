"""RQ tasks for the integrated product-growth workflow."""
from __future__ import annotations

import json
from typing import Any

from app.db import Product, get_db
from app.media.ai_detail_page import generate_detail_images
from app.orchestration.product_growth import (
    _merge_step,
    _product_dict,
    _set_workflow,
    get_workflow,
    register_detail_assets,
)


def run_detail_generation_job(
    workflow_id: int,
    count: int = 3,
    reference_url: str = "",
    apply: bool = True,
) -> dict[str, Any]:
    """Generate reference-grounded product detail images outside the HTTP lifecycle."""
    workflow = get_workflow(int(workflow_id))
    if not workflow:
        raise LookupError("workflow not found")

    _merge_step(workflow_id, "detail_generation", {"ok": True, "status": "running", "count": count})
    try:
        with get_db() as db:
            product = db.get(Product, workflow.product_id)
            if not product:
                raise LookupError("product not found")
            context = _product_dict(product)

        generated = generate_detail_images(
            context,
            count=max(1, min(int(count), 5)),
            reference_url=str(reference_url or ""),
        )
        metadata = [
            {
                "local_path": item.local_path,
                "public_url": item.public_url,
                "prompt": item.prompt,
                "role": item.role,
            }
            for item in generated
        ]
        public_urls = [item.public_url for item in generated if item.public_url]
        _set_workflow(
            workflow_id,
            detail_generated_json=json.dumps(metadata, ensure_ascii=False),
            detail_image_urls_json=json.dumps(public_urls, ensure_ascii=False),
            error="",
        )
        applied = False
        if apply and public_urls:
            register_detail_assets(workflow_id, public_urls, apply=True)
            applied = True
        _merge_step(
            workflow_id,
            "detail_generation",
            {
                "ok": True,
                "status": "completed",
                "generated": len(generated),
                "public_urls": len(public_urls),
                "applied": applied,
            },
        )
        return {
            "ok": True,
            "workflow_id": workflow_id,
            "generated": len(generated),
            "public_urls": public_urls,
            "applied": applied,
        }
    except Exception as exc:
        _set_workflow(workflow_id, error=str(exc)[:4000])
        _merge_step(workflow_id, "detail_generation", {"ok": False, "status": "failed", "error": str(exc)[:2000]})
        raise


__all__ = ["run_detail_generation_job"]
