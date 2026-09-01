"""Compatibility import surface for the product growth workflow service."""
from app.orchestration import product_growth_service as _service
from app.orchestration.product_growth_service import (
    _merge_step,
    _product_dict,
    _set_workflow,
    apply_detail_assets,
    attach_image_generation,
    create_workflow,
    ensure_workflow_tracking,
    get_workflow,
    list_workflows,
    prepare_threads_drafts,
    queue_detail_generation,
    register_detail_assets,
    schedule_workflow_post,
    stage_attached_social_visual,
    tracking_is_public,
    tracking_public_url,
    use_detail_social_visual,
    use_product_social_visual,
    workflow_to_dict,
)

# RQ 2.x guarantees Job.get_status() returns JobStatus.  The service normalizes
# with str(...).lower(), so accept both raw values ("queued") and enum string
# representations ("JobStatus.QUEUED") to keep paid-detail job dedupe reliable.
_service._ACTIVE_RQ_STATES.update(
    {
        "jobstatus.queued",
        "jobstatus.started",
        "jobstatus.deferred",
        "jobstatus.scheduled",
    }
)

__all__ = [
    "create_workflow",
    "get_workflow",
    "list_workflows",
    "workflow_to_dict",
    "ensure_workflow_tracking",
    "prepare_threads_drafts",
    "attach_image_generation",
    "stage_attached_social_visual",
    "use_product_social_visual",
    "use_detail_social_visual",
    "register_detail_assets",
    "apply_detail_assets",
    "queue_detail_generation",
    "schedule_workflow_post",
    "tracking_public_url",
    "tracking_is_public",
]
