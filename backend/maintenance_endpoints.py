from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any
from database import get_database
from maintenance_service import get_maintenance_service

router = APIRouter(prefix="/api/maintenance", tags=["Maintenance"])

from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

@router.post("/windows")
async def create_maintenance_window(window_data: Dict[str, Any], current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")), db=Depends(get_database)):
    tenant_id = get_tenant_id()
    window_data["tenantId"] = tenant_id
    service = get_maintenance_service(db)
    try:
        window = await service.create_window(window_data)
        return {"success": True, "window": window}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/windows")
async def list_maintenance_windows(current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")), db=Depends(get_database)):
    tenant_id = get_tenant_id()
    service = get_maintenance_service(db)
    windows = await service.list_windows(tenant_id)
    return windows

@router.delete("/windows/{window_id}")
async def delete_maintenance_window(window_id: str, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")), db=Depends(get_database)):
    # Note: Service should ideally check tenant ownership of window_id too
    service = get_maintenance_service(db)
    await service.delete_window(window_id)
    return {"success": True}

@router.get("/check")
async def check_maintenance_status(current_user: TokenData = Depends(get_current_user), db=Depends(get_database)):
    tenant_id = get_tenant_id()
    service = get_maintenance_service(db)
    is_in_window = await service.is_in_maintenance_window(tenant_id)
    return {"is_in_window": is_in_window}
