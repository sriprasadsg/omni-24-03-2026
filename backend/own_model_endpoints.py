"""Status of the platform's own from-scratch model (training progress + live usage)."""
import json

from fastapi import APIRouter, Depends

from ai_services import omni_scratch_data as data
from ai_services.omni_scratch_provider import OmniScratchProvider, active_stats
from rbac_utils import require_permission

router = APIRouter(prefix="/api/ai/own-model", tags=["AI"])


@router.get("/status")
async def own_model_status(_current_user=Depends(require_permission("view:system"))):
    training = {}
    if data.STATUS_PATH.exists():
        try:
            training = json.loads(data.STATUS_PATH.read_text())
        except json.JSONDecodeError:
            training = {"stage": "unknown"}
    return {
        "trained_model_available": OmniScratchProvider.available(),
        "teacher": {"url": data.TEACHER_URL, "model": data.TEACHER_MODEL},
        "training": training,
        "serving": active_stats(),
    }
