"""
Compliance Automation API Endpoints

Provides automated evidence collection and continuous compliance monitoring.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from evidence_automation_service import get_evidence_service
from continuous_compliance_service import get_continuous_compliance_service
from rbac_utils import require_permission
from auth_types import TokenData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compliance-automation", tags=["Compliance Automation"])

_COMPLIANCE_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

def _resolve_tenant(current_user, requested: str = None) -> str:
    role = getattr(current_user, "role", "") or (current_user.get("role", "") if isinstance(current_user, dict) else "")
    caller = getattr(current_user, "tenant_id", None) or (current_user.get("tenant_id") if isinstance(current_user, dict) else None)
    if role in _COMPLIANCE_SUPER_ROLES:
        tid = requested or caller
    else:
        tid = caller
    if not tid:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


# Request/Response Models
class EvidenceCollectionRequest(BaseModel):
    framework_id: str


class ComplianceEvaluationRequest(BaseModel):
    framework_id: Optional[str] = None


# Endpoints
@router.post("/collect-evidence")
async def collect_evidence(
    request: EvidenceCollectionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:compliance"))
):
    """
    Collect compliance evidence for a framework.
    Triggers evidence collection on all agents in the caller's tenant.
    """
    tenant_id = _resolve_tenant(current_user)
    agents = await db.agents.find({"tenantId": tenant_id}).to_list(length=1000)

    count = 0
    for agent in agents:
        instruction = {
            "id": f"instr-{uuid.uuid4().hex[:8]}",
            "agent_id": agent["id"],
            "type": "collect_evidence",
            "framework_id": request.framework_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "framework_id": request.framework_id,
                "tenant_id": tenant_id,
            }
        }
        await db.agent_instructions.insert_one(instruction)
        count += 1

    return {
        "success": True,
        "message": f"Evidence collection triggered for {count} agents",
        "framework_id": request.framework_id
    }


class AgentComplianceResult(BaseModel):
    agent_id: str
    framework_id: str
    controls: List[Dict[str, Any]]


@router.post("/submit-agent-results")
async def submit_agent_results(
    result: AgentComplianceResult,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("submit:compliance"))
):
    """
    Receive compliance results from agents
    """
    logger.info("Compliance results from %s for %s", result.agent_id, result.framework_id)

    # Get agent to resolve asset_id and tenant
    agent = await db.agents.find_one({"id": result.agent_id})
    if not agent:
        agent = await db.agents.find_one({"hostname": result.agent_id})

    asset_id = agent["id"] if agent else result.agent_id
    tenant_id = (agent.get("tenantId") if agent else None) or _resolve_tenant(current_user)
    
    for control in result.controls:
        control_id = control.get("id")
        status = control.get("status") # Implemented, Not Implemented, etc.
        # Map agent status to UI status
        if status == "Compliant":
            ui_status = "Compliant"
        else:
            ui_status = "Non-Compliant"
            
        evidence_list = control.get("evidence", [])
        formatted_evidence = []
        
        # Process evidence
        for ev in evidence_list:
             ev_id = f"ev-{uuid.uuid4().hex[:8]}"
             evidence_doc = {
                "id": ev_id,
                "tenant_id": tenant_id,
                "framework_id": result.framework_id,
                "control_id": control_id,
                "asset_id": asset_id,
                "evidence_type": "automated_collection",
                "evidence_data": ev.get("data"),
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "status": "valid"
             }
             await db.compliance_evidence.insert_one(evidence_doc)
             
             formatted_evidence.append({
                 "id": ev_id,
                 "name": ev.get("name", "System Evidence"),
                 "url": "#", # System generated
                 "date": datetime.now(timezone.utc).isoformat(),
                 "systemGenerated": True,
                 "content": ev.get("content") # stored in DB evidence_data usually, but good for UI if small
             })

        # Upsert AssetCompliance record
        await db.asset_compliance.update_one(
            {
                "assetId": asset_id,
                "controlId": control_id,
                "frameworkId": result.framework_id
            },
            {
                "$set": {
                    "assetId": asset_id,
                    "controlId": control_id,
                    "frameworkId": result.framework_id,
                    "status": ui_status,
                    "evidence": formatted_evidence,
                    "lastUpdated": datetime.now(timezone.utc).isoformat(),
                    "reason": control.get("reason"),
                    "remediation": control.get("remediation")
                }
            },
            upsert=True
        )
        
    return {"status": "success"}


@router.post("/evaluate-compliance")
async def evaluate_compliance(
    request: ComplianceEvaluationRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:compliance"))
):
    """
    Evaluate real-time compliance posture
    
    Returns compliance score and violations
    """
    tenant_id = _resolve_tenant(current_user)
    service = get_continuous_compliance_service(db)

    if request.framework_id in service.framework_modules:
        result = await service.evaluate_framework_v2(
            tenant_id=tenant_id,
            framework_id=request.framework_id
        )
    else:
        result = await service.evaluate_compliance(
            tenant_id=tenant_id,
            framework_id=request.framework_id
        )

    return result


@router.get("/compliance-trend")
async def get_compliance_trend(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:compliance"))
):
    """
    Get compliance score trend over time

    Returns historical compliance scores
    """
    service = get_continuous_compliance_service(db)

    trend = await service.get_compliance_trend(
        tenant_id=_resolve_tenant(current_user),
        days=days
    )
    
    return trend


@router.get("/evidence/{framework_id}")
async def get_framework_evidence(
    framework_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:compliance"))
):
    """
    Get all evidence for a compliance framework

    Returns collected evidence with validation status
    """
    cursor = db.compliance_evidence.find({
        "framework_id": framework_id,
        "tenant_id": _resolve_tenant(current_user)
    }).sort("collected_at", -1)
    
    evidence_list = []
    async for evidence in cursor:
        evidence["id"] = str(evidence.pop("_id"))
        evidence_list.append(evidence)
    
    return evidence_list


@router.post("/validate-evidence/{evidence_id}")
async def validate_evidence(
    evidence_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:compliance"))
):
    """
    Validate evidence integrity and freshness

    Returns validation result
    """
    service = get_evidence_service(db)

    result = await service.validate_evidence(
        evidence_id=evidence_id,
        tenant_id=_resolve_tenant(current_user)
    )
    
    return result


@router.post("/create-remediation-task")
async def create_remediation_task(
    violation: Dict[str, Any],
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:compliance"))
):
    """
    Create remediation task for a compliance violation

    Returns created task
    """
    service = get_continuous_compliance_service(db)

    task = await service.create_remediation_task(
        violation=violation,
        tenant_id=_resolve_tenant(current_user)
    )
    
    return task
