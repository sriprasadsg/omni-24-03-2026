import os
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from .training_service import get_training_service
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/ai/train", tags=["AI Training"])


@router.post("/start")
async def start_training(
    model_name: str = "Omni-Local-V1",
    current_user: TokenData = Depends(get_current_user),
):
    """Start QLoRA fine-tuning. Builds dataset automatically if missing."""
    service = get_training_service()
    result = await service.start_training(model_name)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/build-dataset")
async def build_dataset(current_user: TokenData = Depends(get_current_user)):
    """Pull data from MongoDB and write the JSONL training dataset."""
    service = get_training_service()
    result = await service.build_dataset()
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/status")
async def get_training_status(current_user: TokenData = Depends(get_current_user)):
    """Get current training progress, history, model info, and dataset stats."""
    service = get_training_service()
    return service.get_status()


@router.get("/model-info")
async def get_model_info(current_user: TokenData = Depends(get_current_user)):
    """Return info about the currently saved fine-tuned adapter."""
    service = get_training_service()
    return service.get_model_info()


@router.post("/activate")
async def activate_model(current_user: TokenData = Depends(get_current_user)):
    """
    Set OMNI_LOCAL_ENABLED=true so the next AI call uses the fine-tuned model.
    Also re-initialises the IncidentAnalyzer provider chain.
    """
    service = get_training_service()
    info = service.get_model_info()
    if not info.get("trained"):
        raise HTTPException(
            status_code=400,
            detail="No trained adapter found. Run /start first.",
        )

    # Flip the env flag (process-scoped; persists until server restart)
    os.environ["OMNI_LOCAL_ENABLED"] = "true"

    # Re-initialise the live AI service so it picks up the local model immediately
    try:
        from ai_service import ai_service
        ai_service.provider = None
        ai_service.is_configured = False
        await ai_service.initialize()
        active_provider = ai_service.provider.name if ai_service.provider else "unknown"
    except Exception as exc:
        active_provider = f"re-init failed: {exc}"

    return {
        "activated": True,
        "adapter_path": info.get("adapter_path"),
        "active_provider": active_provider,
    }


@router.post("/deactivate")
async def deactivate_model(current_user: TokenData = Depends(get_current_user)):
    """
    Disable the local model so the system falls back to external LLMs.
    """
    os.environ["OMNI_LOCAL_ENABLED"] = "false"
    try:
        from ai_service import ai_service
        ai_service.provider = None
        ai_service.is_configured = False
        await ai_service.initialize()
        active_provider = ai_service.provider.name if ai_service.provider else "unknown"
    except Exception as exc:
        active_provider = f"re-init failed: {exc}"

    return {
        "activated": False,
        "active_provider": active_provider,
    }
