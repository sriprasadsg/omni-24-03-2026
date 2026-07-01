"""Supply Chain Endpoints — /api/supply-chain/*"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from authentication_service import get_current_user
import supply_chain_service

router = APIRouter(prefix="/api/supply-chain", tags=["Supply Chain"])

class ScanRequest(BaseModel):
    packages: list[dict]

@router.post("/scan")
async def scan_packages(req: ScanRequest, current_user=Depends(get_current_user)):
    tenant_id = current_user.tenant_id or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return await supply_chain_service.scan_package_list(req.packages, tenant_id)

@router.get("/findings")
async def list_findings(current_user=Depends(get_current_user)):
    tenant_id = current_user.tenant_id or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return await supply_chain_service.list_findings(tenant_id)
