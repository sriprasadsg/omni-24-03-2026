from fastapi import APIRouter, Depends
from typing import Dict, Any
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/settings", tags=["Settings"])

@router.get("/database")
async def get_database_settings(current_user: TokenData = Depends(get_current_user)):
    """Get database settings"""
    db = get_database()
    settings = await db.system_settings.find_one({"type": "database"}, {"_id": 0})
    return settings or {}

@router.post("/database")
async def save_database_settings(settings: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    """Save database settings"""
    db = get_database()
    # Add type identifier
    settings["type"] = "database"
    await db.system_settings.update_one(
        {"type": "database"},
        {"$set": settings},
        upsert=True
    )
    return settings

@router.get("/llm")
async def get_llm_settings(current_user: TokenData = Depends(get_current_user)):
    """Get LLM settings"""
    db = get_database()
    settings = await db.system_settings.find_one({"type": "llm"}, {"_id": 0})
    return settings or {}

@router.post("/llm")
async def save_llm_settings(settings: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    """Save LLM settings"""
    db = get_database()
    # Add type identifier
    settings["type"] = "llm"
    await db.system_settings.update_one(
        {"type": "llm"},
        {"$set": settings},
        upsert=True
    )
    # Re-initialize AI service if possible (optional, but good practice)
    from ai_service import ai_service
    await ai_service.initialize()
    
    return settings
