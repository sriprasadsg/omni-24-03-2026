from fastapi import APIRouter, Depends
from catalogue_mounts_secops import THREAT_HUNTING_GUARD, THREAT_INTEL_GUARD
from typing import List, Dict, Optional, Any
from pydantic import BaseModel

from ai_threat_service import threat_service

router = APIRouter(prefix="/api/ai", tags=["AI Integration"])

class ThreatHuntRequest(BaseModel):
    query: str
    target_collection: Optional[str] = "metrics" # metrics or logs

class ThreatHuntResponse(BaseModel):
    success: bool
    data: List[Dict[str, Any]]
    generated_pipeline: List[Dict[str, Any]]
    error: Optional[str] = None

from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_utils import require_permission

from virustotal_client import get_virustotal_client

@router.post("/threat-hunt", response_model=ThreatHuntResponse, dependencies=[Depends(THREAT_HUNTING_GUARD)])
async def threat_hunt(request: ThreatHuntRequest, current_user: TokenData = Depends(require_permission("view:threat_hunting"))):
    """
    Execute a natural language threat hunt query.
    """
    tenant_id = get_tenant_id()
    result = await threat_service.process_query(request.query, tenant_id=tenant_id)
    
    return {
        "success": result.get("success", False),
        "data": result.get("data", []),
        "generated_pipeline": result.get("generated_pipeline", []),
        "error": result.get("error")
    }

@router.get("/reputation/ip/{ip}", dependencies=[Depends(THREAT_INTEL_GUARD)])
async def get_ip_reputation(ip: str, current_user: TokenData = Depends(require_permission("view:security"))):
    vt = get_virustotal_client()
    return vt.scan_ip(ip)

@router.get("/reputation/domain/{domain}", dependencies=[Depends(THREAT_INTEL_GUARD)])
async def get_domain_reputation(domain: str, current_user: TokenData = Depends(require_permission("view:security"))):
    vt = get_virustotal_client()
    return vt.scan_domain(domain)

@router.get("/reputation/url", dependencies=[Depends(THREAT_INTEL_GUARD)])
async def get_url_reputation(url: str, current_user: TokenData = Depends(require_permission("view:security"))):
    vt = get_virustotal_client()
    return vt.scan_url(url)
