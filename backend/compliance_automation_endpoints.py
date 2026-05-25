"""
Compliance Automation API Endpoints
"""

import io
import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from typing import List, Dict, Optional
from authentication_service import get_current_user
from compliance_automation_service import compliance_automation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compliance/automation", tags=["Compliance Automation"])

def _get(user, key, default=None):
    """Get a field from either a dict or Pydantic user object."""
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)


def _tenant_id(user):
    """Extract tenant_id correctly from either a dict or TokenData object."""
    if isinstance(user, dict):
        return user.get("tenant_id") or user.get("tenantId") or None
    return getattr(user, "tenant_id", None) or None

@router.post("/generate/patch-compliance")
async def generate_patch_compliance_evidence(
    framework: str = "All",
    current_user = Depends(get_current_user)
) -> Dict:
    """Generate patch compliance evidence"""
    evidence = await compliance_automation.generate_patch_compliance_evidence(
        _tenant_id(current_user),
        framework
    )
    return evidence

@router.post("/generate/vulnerabilities")
async def generate_vulnerability_evidence(
    current_user = Depends(get_current_user)
) -> Dict:
    """Generate vulnerability scan evidence"""
    evidence = await compliance_automation.generate_vulnerability_evidence(
        _tenant_id(current_user)
    )
    return evidence

@router.post("/generate/agent-status")
async def generate_agent_status_evidence(
    current_user = Depends(get_current_user)
) -> Dict:
    """Generate agent status evidence"""
    evidence = await compliance_automation.generate_agent_status_evidence(
        _tenant_id(current_user)
    )
    return evidence

@router.post("/generate/security-alerts")
async def generate_security_alert_evidence(
    days: int = 7,
    current_user = Depends(get_current_user)
) -> Dict:
    """Generate security alert summary evidence"""
    evidence = await compliance_automation.generate_security_alert_evidence(
        _tenant_id(current_user),
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
        _tenant_id(current_user),
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
        _tenant_id(current_user),
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
            _tenant_id(current_user)
        )
        return rules
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).error("Failed to fetch automation rules: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/evidence/package/{framework}")
async def download_evidence_package(
    framework: str,
    current_user = Depends(get_current_user)
):
    """Download evidence package as PDF"""
    pdf_data = await compliance_automation.generate_evidence_package(
        _tenant_id(current_user),
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

        _SUPER_ADMIN_ROLES = {"Super Admin", "super_admin", "superadmin", "platform-admin"}
        caller_tenant = _tenant_id(current_user)
        is_super_admin = _get(current_user, "role", "") in _SUPER_ADMIN_ROLES
        requested_tenant = data.get("tenant_id")
        if requested_tenant and not is_super_admin and requested_tenant != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to evaluate assets for this tenant")
        tenant_id = requested_tenant if (requested_tenant and is_super_admin) else caller_tenant
        framework_id = data.get("framework_id", "all")

        if not tenant_id:
            raise HTTPException(status_code=400, detail="Tenant ID is required")

        result = await evaluate_all_tenant_assets(tenant_id, framework_id)
        return result

    except Exception as e:
        logger.exception("Unhandled exception")
        logger.error("Compliance evaluation failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
