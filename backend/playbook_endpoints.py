from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from pydantic import BaseModel
from playbook_service import playbook_service
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(
    prefix="/api/playbooks",
    tags=["Playbooks"]
)

print("DEBUG: Loading Playbook Endpoints...")

class PlaybookCreate(BaseModel):
    name: str
    description: str
    trigger: str
    steps: List[Dict[str, Any]]

@router.get("", response_model=List[Dict[str, Any]])
async def get_playbooks(current_user: TokenData = Depends(get_current_user)):
    """List playbooks visible to the caller (own tenant + platform-level)."""
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    tenant_id = getattr(current_user, "tenant_id", "default")
    all_playbooks = await playbook_service.get_playbooks()
    if is_admin:
        return all_playbooks
    return [p for p in all_playbooks if p.get("tenant_id", p.get("tenantId", "")) in (tenant_id, "platform")]

@router.get("/test", response_model=Dict[str, str])
async def test_endpoint(_current_user: TokenData = Depends(get_current_user)):
    return {"message": "Playbook Router Active"}

@router.get("/{playbook_id}", response_model=Dict[str, Any])
async def get_playbook(
    playbook_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get details of a specific playbook."""
    playbook = await playbook_service.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    # Non-admins can only view their own tenant's playbooks
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    if not is_admin:
        tenant_id = getattr(current_user, "tenant_id", "default")
        if playbook.get("tenant_id") not in (tenant_id, "platform"):
            raise HTTPException(status_code=404, detail="Playbook not found")
    return playbook

@router.post("/create", response_model=Dict[str, str])
async def create_playbook(
    playbook: PlaybookCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new playbook scoped to the caller's tenant."""
    tenant_id = getattr(current_user, "tenant_id", "default")
    playbook_id = await playbook_service.create_playbook(
        name=playbook.name,
        description=playbook.description,
        trigger=playbook.trigger,
        steps=playbook.steps,
        tenant_id=tenant_id,
    )
    if not playbook_id:
        raise HTTPException(status_code=500, detail="Failed to create playbook")
    return {"id": playbook_id, "message": "Playbook created successfully"}

@router.delete("/{playbook_id}")
async def delete_playbook(
    playbook_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Delete a playbook — non-admins can only delete their own tenant's playbooks."""
    playbook = await playbook_service.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    caller_tenant = getattr(current_user, "tenant_id", "default")
    if not is_admin and playbook.get("tenant_id", playbook.get("tenantId", "")) not in (caller_tenant, "platform"):
        raise HTTPException(status_code=403, detail="Not authorized to delete this playbook")
    success = await playbook_service.delete_playbook(playbook_id)
    if not success:
        raise HTTPException(status_code=500, detail="Delete failed")
    return {"message": "Playbook deleted successfully"}


@router.patch("/{playbook_id}/toggle")
async def toggle_playbook(
    playbook_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Toggle a playbook enabled/disabled state — enforces tenant ownership."""
    existing = await playbook_service.get_playbook(playbook_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Playbook not found")
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    caller_tenant = getattr(current_user, "tenant_id", "default")
    if not is_admin and existing.get("tenant_id", existing.get("tenantId", "")) not in (caller_tenant, "platform"):
        raise HTTPException(status_code=403, detail="Not authorized to modify this playbook")
    playbook = await playbook_service.toggle_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return {
        "id": playbook_id,
        "enabled": playbook.get("enabled"),
        "message": f"Playbook {'enabled' if playbook.get('enabled') else 'disabled'} successfully",
    }


@router.post("/{playbook_id}/execute")
async def execute_playbook(
    playbook_id: str,
    context: Dict[str, Any] = {},
    current_user: TokenData = Depends(get_current_user),
):
    """Execute a playbook — enforces tenant ownership before execution."""
    # Fetch the playbook and verify the caller owns it
    playbook = await playbook_service.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    caller_tenant = getattr(current_user, "tenant_id", "default")
    playbook_tenant = playbook.get("tenant_id", playbook.get("tenantId", ""))

    if not is_admin and playbook_tenant not in (caller_tenant, "platform"):
        raise HTTPException(status_code=403, detail="Not authorized to execute this playbook")

    # Always derive tenant_id from the authenticated token, never from user-supplied context
    context["tenant_id"] = caller_tenant
    context["executed_by"] = getattr(current_user, "username", str(current_user))

    result = await playbook_service.execute_playbook(playbook_id, context)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Execution failed"))
    return result
