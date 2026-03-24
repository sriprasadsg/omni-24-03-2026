from fastapi import APIRouter, HTTPException, Depends
from typing import List
from models import RemediationRequest
from remediation_service import RemediationService
from tenant_context import get_tenant_id


router = APIRouter(prefix="/api/remediation", tags=["AI Remediation"])

# In-Memory Store for Demo (replace with DB later)
REMEDIATION_STORE = {} 

@router.post("/generate", response_model=RemediationRequest)
async def generate_remediation(
    asset_id: str, 
    vulnerability_id: str, 
    cve_id: str,
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Ask the AI to generate a fix for a specific vulnerability.
    """
    try:
        proposal = await RemediationService.generate_fix_proposal(tenant_id, asset_id, vulnerability_id, cve_id)
        REMEDIATION_STORE[proposal.id] = proposal
        return proposal
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{request_id}/execute", response_model=RemediationRequest)
async def execute_remediation(
    request_id: str,
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Approve and execute a pending remediation request.
    """
    proposal = REMEDIATION_STORE.get(request_id)
    
    if not proposal:
        raise HTTPException(status_code=404, detail="Remediation request not found")
        
    if proposal.tenantId != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
        
    try:
        updated_request = await RemediationService.approve_and_execute(proposal)
        return updated_request
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[RemediationRequest])
async def list_remediations(tenant_id: str = Depends(get_tenant_id)):
    """
    Get all remediation requests for the current tenant.
    """
    return [r for r in REMEDIATION_STORE.values() if r.tenantId == tenant_id]
