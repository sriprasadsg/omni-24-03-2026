"""DLP Endpoints — /api/dlp/*"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from authentication_service import get_current_user
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
    content = await file.read()
    return await dlp_service.scan_file_bytes(
        content, file.filename or "unknown",
        current_user.username, current_user.tenant_id or "default"
    )

@router.get("/incidents")
async def list_incidents(status: Optional[str] = None, current_user=Depends(get_current_user)):
    return await dlp_service.list_incidents(current_user.tenant_id or "default", status)

@router.get("/policies")
async def list_policies(current_user=Depends(get_current_user)):
    return await dlp_service.get_policies(current_user.tenant_id or "default")

@router.post("/policies")
async def create_policy(req: PolicyRequest, current_user=Depends(get_current_user)):
    if current_user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    return await dlp_service.create_policy(current_user.tenant_id or "default", req.dict())

@router.patch("/incidents/{scan_id}/resolve")
async def resolve_incident(scan_id: str, current_user=Depends(get_current_user)):
    return await dlp_service.resolve_incident(scan_id, current_user.username)
