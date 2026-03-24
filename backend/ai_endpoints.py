from fastapi import APIRouter, HTTPException, Body, Depends
from typing import Dict, Any
from ai_playbook_service import ai_playbook_service
from ai_remediation_service import ai_remediation_service
from ai_service import ai_service
from authentication_service import get_current_user

router = APIRouter(prefix="/api/ai", tags=["AI Automation"])

from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

@router.get("")
@router.get("/")
async def ai_service_status():
    """Get AI automation service status."""
    return {
        "status": "operational",
        "services": ["remediation", "playbook_generation", "chat_assistant"],
        "version": "1.0.0"
    }


@router.post("/remediation/cspm")
async def generate_cspm_remediation(
    finding: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("remediate:agents"))
):
    """Generate remediation for CSPM finding"""
    return await ai_remediation_service.generate_cspm_remediation(finding)

@router.post("/remediation/iac")
async def generate_iac_fix(
    finding: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("remediate:agents"))
):
    """Generate IaC fix for CSPM finding"""
    return await ai_remediation_service.generate_iac_fix(finding)

@router.post("/chat")
async def chat_assistant(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))
):
    """Chat with AI Assistant"""
    message = payload.get("message")
    context = payload.get("context", {})
    # Inject tenant_id into context for scoped chat if needed
    context["tenantId"] = get_tenant_id()
    return {"response": await ai_service.chat(message, context)}

@router.post("/generate-playbook")
async def generate_playbook(
    payload: Dict[str, str] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:security_playbooks"))
):
    """Generate a playbook using AI"""
    prompt = payload.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
        
    tenant_id = get_tenant_id()
    
    playbook = await ai_playbook_service.generate_playbook(prompt, tenant_id)
    return playbook
