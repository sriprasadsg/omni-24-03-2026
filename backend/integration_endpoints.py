from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from database import get_database
from integration_service import get_integration_service

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])

# --- Models ---
class IntegrationConfig(BaseModel):
    type: str # siem, chatops, ticketing
    platform: str # splunk, slack, jira
    enabled: bool
    endpoint: Optional[str] = None
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    webhook_url: Optional[str] = None
    instance_url: Optional[str] = None
    api_key: Optional[str] = None
    project_key: Optional[str] = None
    
class TestIntegrationRequest(BaseModel):
    type: str
    platform: str
    config: Dict[str, Any]

# --- Endpoints ---

@router.get("/configs")
async def get_integration_configs(
    tenant_id: Optional[str] = "default",  # MVP default
    db=Depends(get_database)
):
    """Get all integration configs for tenant"""
    service = get_integration_service(db)
    return await service.get_all_configs(tenant_id)

@router.post("/config")
async def save_integration_config(
    config: IntegrationConfig,
    tenant_id: Optional[str] = "default",
    db=Depends(get_database)
):
    """Save integration config"""
    service = get_integration_service(db)
    result = await service.save_config(tenant_id, config.dict())
    return result

@router.post("/test")
async def test_integration(
    request: TestIntegrationRequest,
    db=Depends(get_database)
):
    """Test integration connection"""
    service = get_integration_service(db)
    
    if request.type == "siem":
        return await service.test_siem_connection(request.platform, request.config)
    elif request.type == "chatops":
        return await service.send_to_chatops(
            title="Integration Test",
            message=f"This is a test message from Omni-Agent Platform to {request.platform}.",
            severity="info",
            platform=request.platform
        )
    else:
        return {"success": False, "error": f"Testing not supported for {request.type}"}
