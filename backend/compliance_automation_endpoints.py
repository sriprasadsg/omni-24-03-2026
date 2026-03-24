"""
Compliance Automation API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from typing import List, Dict, Optional
from authentication_service import get_current_user
from compliance_automation_service import compliance_automation
import io

router = APIRouter(prefix="/api/compliance/automation", tags=["Compliance Automation"])

def _get(user, key, default=None):
    """Get a field from either a dict or Pydantic user object."""
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)

@router.post("/generate/patch-compliance")
async def generate_patch_compliance_evidence(
    framework: str = "All",
    current_user = Depends(get_current_user)
) -> Dict:
    """Generate patch compliance evidence"""
    evidence = await compliance_automation.generate_patch_compliance_evidence(
        _get(current_user, "tenantId", "default"),
        framework
    )
    return evidence

@router.post("/generate/vulnerabilities")
async def generate_vulnerability_evidence(
    current_user = Depends(get_current_user)
) -> Dict:
    """Generate vulnerability scan evidence"""
    evidence = await compliance_automation.generate_vulnerability_evidence(
        _get(current_user, "tenantId", "default")
    )
    return evidence

@router.post("/generate/agent-status")
async def generate_agent_status_evidence(
    current_user = Depends(get_current_user)
) -> Dict:
    """Generate agent status evidence"""
    evidence = await compliance_automation.generate_agent_status_evidence(
        _get(current_user, "tenantId", "default")
    )
    return evidence

@router.post("/generate/security-alerts")
async def generate_security_alert_evidence(
    days: int = 7,
    current_user = Depends(get_current_user)
) -> Dict:
    """Generate security alert summary evidence"""
    evidence = await compliance_automation.generate_security_alert_evidence(
        _get(current_user, "tenantId", "default"),
        days
    )
    return evidence

@router.get("/evidence/{evidence_type}")
async def get_evidence(
    evidence_type: str,
    limit: int = 10,
    current_user = Depends(get_current_user)
) -> List[Dict]:
    """Get collected evidence by type"""
    evidence = await compliance_automation.get_evidence_by_type(
        _get(current_user, "tenantId", "default"),
        evidence_type,
        limit
    )
    return evidence

@router.post("/rules")
async def create_automation_rule(
    rule: Dict,
    current_user = Depends(get_current_user)
) -> Dict:
    """Create automated evidence collection rule"""
    created_rule = await compliance_automation.create_automation_rule(
        _get(current_user, "tenantId", "default"),
        rule
    )
    return created_rule

@router.get("/rules")
async def get_automation_rules(
    current_user = Depends(get_current_user)
) -> List[Dict]:
    """Get all automation rules"""
    try:
        rules = await compliance_automation.get_automation_rules(
            _get(current_user, "tenantId", "default")
        )
        return rules
    except Exception:
        return []

@router.get("/evidence/package/{framework}")
async def download_evidence_package(
    framework: str,
    current_user = Depends(get_current_user)
):
    """Download evidence package as PDF"""
    pdf_data = await compliance_automation.generate_evidence_package(
        _get(current_user, "tenantId", "default"),
        framework
    )

    return StreamingResponse(
        io.BytesIO(pdf_data),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=compliance_evidence_{framework}.pdf"
        }
    )


# NEW: Bulk compliance evaluation endpoint
@router.post("/evaluate-all")
async def evaluate_all_tenant_assets_endpoint(
    data: Dict,
    current_user = Depends(get_current_user)
) -> Dict:
    """
    Evaluate all assets for a tenant against compliance controls
    """
    try:
        from trigger_compliance_check import evaluate_all_tenant_assets

        tenant_id = data.get("tenant_id", _get(current_user, "tenantId", "default"))
        framework_id = data.get("framework_id", "all")

        if not tenant_id:
            raise HTTPException(status_code=400, detail="Tenant ID is required")

        result = await evaluate_all_tenant_assets(tenant_id, framework_id)
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")
