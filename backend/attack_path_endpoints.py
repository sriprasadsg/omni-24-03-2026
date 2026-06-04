from fastapi import APIRouter, Depends, HTTPException
from authentication_service import get_current_user
from attack_path_service import get_attack_path_service
from database import get_database

router = APIRouter(prefix="/api/security", tags=["Security - Attack Paths"])

@router.get("/attack-paths")
async def get_attack_paths(
    current_user: dict = Depends(get_current_user)
):
    """Get identified attack paths for the tenant."""
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context not found")
    db = get_database()
    service = get_attack_path_service(db)
    return await service.get_attack_paths(tenant_id)
