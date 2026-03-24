"""Supply Chain Endpoints — /api/supply-chain/*"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from authentication_service import get_current_user
import supply_chain_service
from typing import Optional

router = APIRouter(prefix="/api/supply-chain", tags=["Supply Chain"])

class ScanRequest(BaseModel):
    packages: list[dict]

@router.post("/scan")
async def scan_packages(req: ScanRequest, current_user=Depends(get_current_user)):
    return await supply_chain_service.scan_package_list(
        req.packages, current_user.tenant_id or "default"
    )

@router.get("/findings")
async def list_findings(current_user=Depends(get_current_user)):
    return await supply_chain_service.list_findings(current_user.tenant_id or "default")
