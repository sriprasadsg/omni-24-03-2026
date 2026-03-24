from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Dict, Any
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_service import rbac_service
import prompt_service

router = APIRouter(prefix="/api/prompts", tags=["Prompts"])

@router.get("", response_model=List[Dict[str, Any]])
async def list_prompts(current_user: TokenData = Depends(rbac_service.has_permission("view:ai_governance"))):
    """
    List all prompt templates.
    """
    return await prompt_service.list_prompts()

@router.post("", response_model=Dict[str, Any])
async def create_prompt(
    prompt: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks"))
):
    """
    Create a new prompt template.
    """
    try:
        return await prompt_service.create_prompt(prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{name}", response_model=Dict[str, Any])
async def get_prompt(
    name: str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:ai_governance"))
):
    """
    Get a prompt template by name.
    """
    prompt = await prompt_service.get_prompt(name)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt

@router.put("/{name}", response_model=Dict[str, Any])
async def update_prompt(
    name: str,
    updates: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks"))
):
    """
    Update a prompt template.
    """
    updated = await prompt_service.update_prompt(name, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return updated

@router.delete("/{name}")
async def delete_prompt(
    name: str,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks"))
):
    """
    Delete a prompt template.
    """
    success = await prompt_service.delete_prompt(name)
    if not success:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"success": True, "message": f"Prompt '{name}' deleted"}
