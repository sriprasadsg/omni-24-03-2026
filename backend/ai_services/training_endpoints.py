from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from .training_service import get_training_service
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/ai/train", tags=["AI Training"])

@router.post("/start")
async def start_training(model_name: str = "Omni-LLM-Scratch-V1", current_user: TokenData = Depends(get_current_user)):
    """Start the scratch training process for Omni-LLM"""
    service = get_training_service()
    result = await service.start_training(model_name)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/status")
async def get_training_status(current_user: TokenData = Depends(get_current_user)):
    """Get current training metrics and progress"""
    service = get_training_service()
    return service.get_status()
