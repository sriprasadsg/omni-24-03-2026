from fastapi import APIRouter, Depends, HTTPException, Path
from database import get_database
from maintenance_service import (TimeZoneBody, WindowBody, WindowError, WindowNotFound,
                                 get_maintenance_service)

router = APIRouter(prefix="/api/maintenance", tags=["Maintenance"])

from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

_WINDOW_ID = Path(..., min_length=1, max_length=64)


def _tenant() -> str:
    """The caller's tenant from the request context, never from a body."""
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No organization is selected.")
    return tenant_id


@router.post("/windows", status_code=201)
async def create_maintenance_window(body: WindowBody, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")), db=Depends(get_database)):
    tenant_id = _tenant()
    try:
        window = await get_maintenance_service(db).create_window(tenant_id, body)
    except WindowError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"success": True, "window": window}


@router.put("/windows/{window_id}")
async def update_maintenance_window(body: WindowBody, window_id: str = _WINDOW_ID, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")), db=Depends(get_database)):
    tenant_id = _tenant()
    try:
        window = await get_maintenance_service(db).update_window(tenant_id, window_id, body)
    except WindowNotFound:
        raise HTTPException(status_code=404, detail="Maintenance window not found")
    except WindowError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"success": True, "window": window}


@router.get("/windows")
async def list_maintenance_windows(current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")), db=Depends(get_database)):
    return await get_maintenance_service(db).list_windows(_tenant())


@router.delete("/windows/{window_id}")
async def delete_maintenance_window(window_id: str = _WINDOW_ID, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")), db=Depends(get_database)):
    if not await get_maintenance_service(db).delete_window(window_id, _tenant()):
        raise HTTPException(status_code=404, detail="Maintenance window not found")
    return {"success": True}


@router.get("/time-zone")
async def get_maintenance_time_zone(current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")), db=Depends(get_database)):
    return {"timeZone": await get_maintenance_service(db).get_time_zone(_tenant())}


@router.put("/time-zone")
async def set_maintenance_time_zone(body: TimeZoneBody, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")), db=Depends(get_database)):
    tenant_id = _tenant()
    try:
        zone = await get_maintenance_service(db).set_time_zone(tenant_id, body.timeZone)
    except WindowError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"timeZone": zone}


@router.get("/status")
async def maintenance_window_status(current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")), db=Depends(get_database)):
    return await get_maintenance_service(db).status(_tenant())


@router.get("/check")
async def check_maintenance_status(current_user: TokenData = Depends(get_current_user), db=Depends(get_database)):
    is_in_window = await get_maintenance_service(db).is_in_maintenance_window(_tenant())
    return {"is_in_window": is_in_window}
