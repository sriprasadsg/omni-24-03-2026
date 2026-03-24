from fastapi import APIRouter, Depends, Query
from typing import List, Dict, Any
from authentication_service import get_current_user
from attack_path_service import get_attack_path_service
from database import get_database

router = APIRouter(prefix="/api/security", tags=["Security - Attack Paths"])

@router.get("/attack-paths")
async def get_attack_paths(
    tenant_id: str = None,
    current_user: dict = Depends(get_current_user)
):
    """Get identified attack paths for the tenant."""
    db = get_database()
    service = get_attack_path_service(db)
    return await service.get_attack_paths(tenant_id)
