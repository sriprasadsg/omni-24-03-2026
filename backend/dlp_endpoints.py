"""DLP Endpoints — /api/dlp/*"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from authentication_service import get_current_user
from database import get_database
import dlp_service
from typing import Optional

router = APIRouter(prefix="/api/dlp", tags=["DLP"])

class PolicyRequest(BaseModel):
    name: str
    pattern: str
    severity: str = "medium"
    action: str = "alert"

class ResolveRequest(BaseModel):
    scan_id: str

@router.post("/scan")
async def scan_file(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")
    content = await file.read()
    return await dlp_service.scan_file_bytes(
        content, file.filename or "unknown",
        current_user.username, current_user.tenant_id or None
    )

@router.get("/incidents")
async def list_incidents(status: Optional[str] = None, current_user=Depends(get_current_user)):
    return await dlp_service.list_incidents(current_user.tenant_id or None, status)

@router.get("/policies")
async def list_policies(current_user=Depends(get_current_user)):
    return await dlp_service.get_policies(current_user.tenant_id or None)

_ADMIN_ROLES = {"Admin", "admin", "Super Admin", "superadmin", "super_admin", "platform-admin"}

@router.post("/policies")
async def create_policy(req: PolicyRequest, current_user=Depends(get_current_user)):
    if getattr(current_user, "role", "") not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin only")
    return await dlp_service.create_policy(current_user.tenant_id or None, req.dict())

@router.patch("/incidents/{scan_id}/resolve")
async def resolve_incident(scan_id: str, current_user=Depends(get_current_user)):
    tenant_id = getattr(current_user, "tenant_id", None)
    caller_role = getattr(current_user, "role", "")
    is_super = caller_role in {"Super Admin", "super_admin", "platform-admin"}
    if not is_super:
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        db = get_database()
        incident = await db.dlp_incidents.find_one({"scan_id": scan_id}, {"_id": 0, "tenant_id": 1})
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if incident.get("tenant_id") != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
    return await dlp_service.resolve_incident(scan_id, current_user.username)
