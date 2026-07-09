import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from authentication_service import get_current_user
from compliance_reporting_data import _build_report_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/oscal", tags=["OSCAL Export"])

_IMPL_STATUS = {
    "Compliant": "implemented",
    "Implemented": "implemented",
    "Pass": "implemented",
    "Passed": "implemented",
    "Non-Compliant": "planned",
    "Fail": "planned",
    "Failed": "planned",
    "Not Implemented": "planned",
    "Warning": "partial",
    "Partially Compliant": "partial",
    "In Progress": "partial",
}

def _to_oscal_assessment_results(framework: dict, control_rows: list) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "assessment-results": {
            "uuid": str(uuid.uuid4()),
            "metadata": {
                "title": framework.get("name", framework.get("id", "Unknown Framework")),
                "last-modified": now.isoformat(),
                "version": "1.0.0",
                "oscal-version": "1.1.2",
            },
            "import-ap": {"source": f"urn:uuid:{framework.get('id', 'unknown')}"},
            "results": [
                {
                    "uuid": str(uuid.uuid4()),
                    "title": f"Assessment of {framework.get('name', framework.get('id', 'Unknown Framework'))}",
                    "start": now.isoformat(),
                    "reviewed-controls": {"control-selections": [{"include-all": {}}]},
                    "findings": _build_findings(control_rows),
                }
            ],
        }
    }

def _build_findings(control_rows: list) -> list:
    findings = []
    for row in control_rows:
        control_id = row.get("Control ID", "")
        control_name = row.get("Control Name", control_id)
        status = row.get("Control Status", "Warning")
        evidence_desc = row.get("Evidence Desc", "")
        impl_status = _IMPL_STATUS.get(status, "partial")

        finding = {
            "uuid": str(uuid.uuid4()),
            "title": f"{control_id}: {control_name}",
            "description": evidence_desc or f"Control {control_id} assessment",
            "target": [{"type": "control", "ref": control_id}],
            "status": {"state": impl_status},
        }

        # Add gap note for Non-Compliant controls (planned status)
        if impl_status == "planned":
            finding["remarks"] = f"Gap: Control {control_id} is {status}"

        findings.append(finding)

    return findings

@router.get("/assessment-results")
async def oscal_assessment_results(
    framework_id: str = Query(...),
    current_user=Depends(get_current_user),
):
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    try:
        framework, asset_summary, control_rows = await _build_report_data(framework_id, tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _to_oscal_assessment_results(framework, control_rows)