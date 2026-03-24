from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pydantic import BaseModel
from authentication_service import get_current_user

router = APIRouter(prefix="/api/roles", tags=["Role Management"])

class Role(BaseModel):
    id: str
    name: str
    description: str
    permissions: List[str]

@router.get("", response_model=List[Role])
async def list_roles(current_user: dict = Depends(get_current_user)):
    """
    List available roles.
    """
    # Static roles for now
    return [
        {
            "id": "admin",
            "name": "Admin",
            "description": "Full access to all resources",
            "permissions": ["all"]
        },
        {
            "id": "user",
            "name": "User",
            "description": "Standard user access",
            "permissions": ["read:agents", "read:assets"]
        },
        {
            "id": "viewer",
            "name": "Viewer",
            "description": "Read-only access",
            "permissions": ["read:all"]
        }
    ]
