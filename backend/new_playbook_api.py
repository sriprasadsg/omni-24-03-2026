from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from pydantic import BaseModel
from playbook_service import playbook_service

router = APIRouter(
    prefix="/api/playbooks",
    tags=["Playbooks"]
)

print("DEBUG: Loading NEW Playbook API...")

class PlaybookCreate(BaseModel):
    name: str
    description: str
    trigger: str
    steps: List[Dict[str, Any]]

@router.get("", response_model=List[Dict[str, Any]])
async def get_playbooks():
    """List all available playbooks."""
    return await playbook_service.get_playbooks()

@router.get("/{playbook_id}", response_model=Dict[str, Any])
async def get_playbook(playbook_id: str):
    """Get details of a specific playbook."""
    playbook = await playbook_service.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return playbook

@router.get("/test", response_model=Dict[str, str])
async def test_endpoint():
    return {"message": "Playbook Router Active"}

@router.post("/create")
async def create_playbook(playbook: PlaybookCreate):
    """Create a new playbook."""
    playbook_id = await playbook_service.create_playbook(
        name=playbook.name,
        description=playbook.description,
        trigger=playbook.trigger,
        steps=playbook.steps
    )
    if not playbook_id:
        raise HTTPException(status_code=500, detail="Failed to create playbook")
    return {"id": playbook_id, "message": "Playbook created successfully"}

@router.delete("/{playbook_id}")
async def delete_playbook(playbook_id: str):
    """Delete a playbook."""
    success = await playbook_service.delete_playbook(playbook_id)
    if not success:
        raise HTTPException(status_code=404, detail="Playbook not found or delete failed")
    return {"message": "Playbook deleted successfully"}
